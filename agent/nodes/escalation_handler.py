"""
Escalation Handler Node — Deterministic CRM Case Creation

Triggered when:
  1. policy_validation_node sets escalation_required=True (pre-flight)
  2. deterministic_executor_node sets escalation_required=True (mid-execution)
  3. Customer explicitly requests human escalation

This node creates a CRM support case with:
  - Full context of what was completed before escalation
  - The escalation reason
  - The trace_id for audit linkage (required for compliance)
  - Appropriate priority level

This is a deterministic node — no LLM involved.
The CRM case is always created via the crm tool's create_case operation.
"""

import time
from typing import Any, Dict, List

from agent.state import AgentState, ToolCallRecord
from guardrails.escalation import build_escalation_case
from tools.registry import get_tool_registry
from utils.logger import logger
from utils.tracing import utcnow


def _ms_since(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)


async def escalation_handler_node(state: AgentState) -> Dict[str, Any]:
    """
    Create a CRM support case for human agent review.

    Reads the full tool_results history to summarise what was completed
    before escalation, providing the human agent with complete context.

    Includes the trace_id in every CRM case for audit linkage — this
    allows the case and the interaction trace to be correlated in any
    monitoring or compliance system.

    Returns:
        Partial AgentState with tool_results updated (CRM case record added),
        node_latencies and node_transitions updated.
    """
    t0 = time.perf_counter()
    trace_id = state.get("trace_id", "")
    customer_id = state.get("customer_id", "CUST-001")
    escalation_reason = state.get("escalation_reason", "Escalation required")

    tools = get_tool_registry()
    tool_results: List[ToolCallRecord] = list(state.get("tool_results", []))

    # Collect successful actions completed before escalation (for CRM context)
    completed_actions = [
        tr["data"].get("message", "")
        for tr in tool_results
        if tr.get("result") == "success" and tr.get("tool") != "crm" and tr.get("data")
    ]

    # Build CRM case payload using existing guardrails/escalation.py helper
    escalation_info = {
        "needs_escalation": True,
        "reason": escalation_reason,
        "priority": "high",
    }
    case_params = build_escalation_case(
        customer_id=customer_id,
        trace_id=trace_id,
        escalation_info=escalation_info,
        completed_actions=completed_actions,
    )

    logger.info(
        "Creating CRM escalation case",
        trace_id=trace_id,
        customer_id=customer_id,
        reason=escalation_reason,
        completed_actions=len(completed_actions),
    )

    # Execute CRM create_case
    crm_tool = tools.get("crm")
    if crm_tool:
        crm_result = await crm_tool.execute(case_params)
    else:
        crm_result = {
            "status": "error",
            "message": "CRM tool unavailable",
            "case_id": "CASE-UNAVAILABLE",
        }

    case_id = crm_result.get("case_id", "CASE-UNKNOWN")

    tool_results.append(ToolCallRecord(
        tool="crm",
        operation="create_case",
        params=case_params,
        result=crm_result.get("status", "error"),
        data=crm_result,
        latency_ms=0,
        retry_count=0,
        timestamp=utcnow(),
    ))

    logger.info(
        "CRM escalation case created",
        trace_id=trace_id,
        case_id=case_id,
        status=crm_result.get("status"),
    )

    latency = _ms_since(t0)
    existing_latencies = dict(state.get("node_latencies", {}))
    existing_latencies["escalation_handler"] = latency

    existing_transitions = list(state.get("node_transitions", []))
    existing_transitions.append("escalation_handler")

    return {
        "tool_results": tool_results,
        "node_latencies": existing_latencies,
        "node_transitions": existing_transitions,
    }
