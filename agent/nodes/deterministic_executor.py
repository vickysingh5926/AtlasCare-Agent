"""
Deterministic Executor Node — The ONLY Tool Dispatcher

This is the most critical node in the entire architecture.

GOVERNANCE INVARIANT:
  The LLM NEVER directly calls tools. This node is the SOLE tool dispatcher.
  It owns 100% of tool dispatch, retry logic, idempotency enforcement,
  per-tool latency tracking, and partial-failure handling.

Execution flow per WorkflowStep:
  1. Check causal dependency satisfaction (skip if predecessor failed)
  2. Check idempotency key (skip duplicate operations)
  3. Run pre-execution refund guardrail (hard-coded, defense-in-depth)
  4. Execute tool via resilience wrapper (timeout + retry + circuit breaker)
  5. Record ToolCallRecord with full metadata
  6. Run post-execution escalation detection
  7. Continue to next step (partial failure is recorded, not fatal)

Partial failure strategy:
  - Each step is evaluated independently
  - Failed steps are recorded in failed_steps[]
  - Succeeding steps continue (e.g., address update proceeds even if refund blocked)
  - The response_generator_node synthesises an accurate summary of partial outcomes
"""

import time
from typing import Any, Dict, List, Set

from agent.state import AgentState, ToolCallRecord, WorkflowStep
from guardrails.refund_limit import check_refund_threshold
from guardrails.escalation import detect_escalation
from tools.registry import get_tool_registry
from utils.resilience import execute_with_resilience
from utils.logger import logger
from utils.tracing import utcnow


def _ms_since(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)


def _op_key(step: WorkflowStep) -> str:
    """Generate a stable idempotency key for a workflow step."""
    params = step.get("params", {})
    return (
        f"{step['tool']}:"
        f"{step['operation']}:"
        f"{params.get('order_id', '')}:"
        f"{params.get('item_index', '')}"
    )


async def deterministic_executor_node(state: AgentState) -> Dict[str, Any]:
    """
    Execute the workflow plan deterministically, step-by-step.

    This node iterates through state["workflow_plan"] in order.
    Each step is subject to:
      - Dependency check (causal ordering)
      - Idempotency guard (no duplicate operations)
      - Pre-execution refund guardrail (₹25K hard limit)
      - Resilience wrapper (timeout + retry + circuit breaker)
      - Post-execution escalation detection

    All outcomes — success, failure, blocked, skipped — are recorded
    in tool_results as ToolCallRecords for the audit trail.

    Returns:
        Partial AgentState with tool_results, completed_steps, failed_steps,
        skipped_steps, executed_ops, retry_counts, escalation flags updated.
    """
    t0 = time.perf_counter()
    trace_id = state.get("trace_id", "")
    customer_id = state.get("customer_id", "CUST-001")

    tools = get_tool_registry()
    plan: List[WorkflowStep] = state.get("workflow_plan", [])

    tool_results: List[ToolCallRecord] = list(state.get("tool_results", []))
    executed_ops: Set[str] = set(state.get("executed_ops", []))
    completed_steps: List[int] = list(state.get("completed_steps", []))
    failed_steps: List[int] = list(state.get("failed_steps", []))
    skipped_steps: List[int] = list(state.get("skipped_steps", []))
    retry_counts: Dict[str, int] = dict(state.get("retry_counts", {}))
    escalation_required: bool = state.get("escalation_required", False)
    escalation_reason: str = state.get("escalation_reason", "")

    logger.info(
        "Deterministic executor started",
        trace_id=trace_id,
        steps=len(plan),
    )

    for step in plan:
        step_num = step["step"]
        tool_name = step["tool"]
        operation = step["operation"]
        params = step["params"]
        deps = step.get("depends_on", [])

        # ── 1. Dependency check ───────────────────────────────────────────
        unsatisfied = [d for d in deps if d not in completed_steps]
        if unsatisfied:
            logger.warning(
                "Step skipped: dependency not satisfied",
                trace_id=trace_id,
                step=step_num,
                tool=tool_name,
                unsatisfied_deps=unsatisfied,
            )
            skipped_steps.append(step_num)
            tool_results.append(ToolCallRecord(
                tool=tool_name,
                operation=operation,
                params=params,
                result="skipped",
                data={"reason": f"Dependency steps {unsatisfied} did not complete successfully"},
                latency_ms=0,
                retry_count=0,
                timestamp=utcnow(),
            ))
            continue

        # ── 2. Idempotency check ──────────────────────────────────────────
        op_key = _op_key(step)
        if op_key in executed_ops:
            logger.warning(
                "Step skipped: duplicate operation (idempotency)",
                trace_id=trace_id,
                step=step_num,
                tool=tool_name,
                op_key=op_key,
            )
            skipped_steps.append(step_num)
            tool_results.append(ToolCallRecord(
                tool=tool_name,
                operation=operation,
                params=params,
                result="skipped",
                data={"reason": "This operation was already executed in this session"},
                latency_ms=0,
                retry_count=0,
                timestamp=utcnow(),
            ))
            continue

        # ── 3. Pre-execution refund guardrail (DEFENSE-IN-DEPTH) ──────────
        # This is the SECOND refund check (policy_validation_node is the first).
        # Both checks use the same hard-coded REFUND_AUTO_LIMIT constant.
        guard = check_refund_threshold(tool_name, params)
        if guard.get("blocked"):
            reason = guard["reason"]
            logger.warning(
                "Guardrail BLOCKED step pre-execution",
                trace_id=trace_id,
                step=step_num,
                tool=tool_name,
                reason=reason,
            )
            failed_steps.append(step_num)
            if not escalation_required:
                escalation_required = True
                escalation_reason = reason

            tool_results.append(ToolCallRecord(
                tool=tool_name,
                operation=operation,
                params=params,
                result="blocked",
                data={"reason": reason, "action": "escalate_to_human"},
                latency_ms=0,
                retry_count=0,
                timestamp=utcnow(),
            ))
            continue

        # ── 4. Tool not found ─────────────────────────────────────────────
        if tool_name not in tools:
            logger.error(
                "Tool not found in registry",
                trace_id=trace_id,
                step=step_num,
                tool=tool_name,
            )
            failed_steps.append(step_num)
            tool_results.append(ToolCallRecord(
                tool=tool_name,
                operation=operation,
                params=params,
                result="error",
                data={"reason": f"Tool '{tool_name}' not found in registry"},
                latency_ms=0,
                retry_count=0,
                timestamp=utcnow(),
            ))
            continue

        # ── 5. Execute with resilience wrapper ────────────────────────────
        tool_t0 = time.perf_counter()
        result = await execute_with_resilience(tools[tool_name], params)
        tool_latency = _ms_since(tool_t0)

        retry_count = result.get("retry_count", 0)
        if retry_count > 0:
            retry_counts[tool_name] = retry_counts.get(tool_name, 0) + retry_count

        executed_ops.add(op_key)

        logger.info(
            "Tool executed",
            trace_id=trace_id,
            step=step_num,
            tool=tool_name,
            operation=operation,
            status=result.get("status"),
            latency_ms=tool_latency,
            retry_count=retry_count,
        )

        # ── 6. Record result ──────────────────────────────────────────────
        outcome = result.get("status", "error")
        tool_results.append(ToolCallRecord(
            tool=tool_name,
            operation=operation,
            params=params,
            result=outcome,
            data=result,
            latency_ms=tool_latency,
            retry_count=retry_count,
            timestamp=utcnow(),
        ))

        if outcome == "success":
            completed_steps.append(step_num)
        else:
            failed_steps.append(step_num)

        # ── 7. Post-execution escalation check ────────────────────────────
        esc = detect_escalation(tool_name, params, result)
        if esc["needs_escalation"] and not escalation_required:
            escalation_required = True
            escalation_reason = esc.get("reason", "Escalation required post-execution")
            logger.info(
                "Post-execution escalation triggered",
                trace_id=trace_id,
                tool=tool_name,
                reason=escalation_reason,
            )

    total_latency = _ms_since(t0)
    existing_latencies = dict(state.get("node_latencies", {}))
    existing_latencies["deterministic_executor"] = total_latency

    existing_transitions = list(state.get("node_transitions", []))
    existing_transitions.append("deterministic_executor")

    logger.info(
        "Deterministic executor completed",
        trace_id=trace_id,
        steps_total=len(plan),
        completed=len(completed_steps),
        failed=len(failed_steps),
        skipped=len(skipped_steps),
        escalation_required=escalation_required,
        latency_ms=total_latency,
    )

    return {
        "tool_results": tool_results,
        "completed_steps": completed_steps,
        "failed_steps": failed_steps,
        "skipped_steps": skipped_steps,
        "executed_ops": list(executed_ops),
        "retry_counts": retry_counts,
        "escalation_required": escalation_required,
        "escalation_reason": escalation_reason,
        "node_latencies": existing_latencies,
        "node_transitions": existing_transitions,
    }
