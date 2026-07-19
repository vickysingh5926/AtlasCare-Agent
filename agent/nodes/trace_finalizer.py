"""
Trace Finalizer Node — Observability, Metrics, and Audit Commit

The final node in every workflow execution. Responsibilities:
  1. Compute final end-to-end latency
  2. Build NodeSpan records from node_latencies
  3. Build WorkflowSummary for operations dashboards
  4. Emit structured log with full workflow metrics
  5. Commit the enriched trace to the in-memory trace store

Observability signals emitted:
  - Per-node latency (node_spans)
  - Workflow summary (steps_planned, completed, failed, skipped)
  - Escalation flag
  - Retry counts per tool
  - Full node traversal path
  - Policy violations
  - Total latency

Extension points (documented, not implemented):
  - Prometheus counter/histogram pushes
  - OpenTelemetry span export
  - Async Kafka event emit for downstream analytics
"""

import time
from typing import Any, Dict, List

from agent.state import AgentState, ToolCallRecord
from models.schemas import NodeSpan, WorkflowSummary, TraceInfo, ToolCallInfo
from utils.logger import logger
from utils.tracing import utcnow

# In-memory trace store (same store used by get_trace() in orchestrator.py)
# Imported here so trace_finalizer can write to it without circular imports.
from agent import _trace_store


def _ms_since(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)


async def trace_finalizer_node(state: AgentState) -> Dict[str, Any]:
    """
    Commit the enriched trace and emit observability metrics.

    Converts internal AgentState records into public-facing Pydantic models
    (TraceInfo, NodeSpan, WorkflowSummary) and stores the trace in the
    in-memory store for the GET /trace/{trace_id} endpoint.

    Returns:
        Empty dict (terminal node — no further state mutations needed).
    """
    t0 = time.perf_counter()
    trace_id = state.get("trace_id", "")
    session_id = state.get("session_id", "")

    # ── Compute total latency ─────────────────────────────────────────────
    start_ns = state.get("start_time_ns", 0)
    if start_ns:
        total_latency_ms = int((time.monotonic_ns() - start_ns) / 1_000_000)
    else:
        # Fallback: sum of all node latencies
        total_latency_ms = sum(state.get("node_latencies", {}).values())

    # ── Build NodeSpan records ────────────────────────────────────────────
    node_latencies = state.get("node_latencies", {})
    node_spans = [
        NodeSpan(
            node=node_name,
            latency_ms=latency_ms,
            timestamp=utcnow(),
        )
        for node_name, latency_ms in node_latencies.items()
    ]

    # ── Convert ToolCallRecords to ToolCallInfo (public API model) ────────
    # Filter out guardrail-blocked records — these are internal audit artifacts.
    # The API contract expects that a tool blocked by the refund guardrail
    # "does not appear in trace" because it was never actually dispatched.
    tool_call_infos: List[ToolCallInfo] = []
    for tr in state.get("tool_results", []):
        if tr.get("result") == "blocked":
            continue  # Blocked tools are not exposed in public trace
        tool_call_infos.append(ToolCallInfo(
            tool=tr.get("tool", "unknown"),
            params=tr.get("params", {}),
            result=tr.get("result", "unknown"),
            data=tr.get("data"),
            timestamp=tr.get("timestamp", utcnow()),
        ))

    # ── Determine primary intent and workflow type ─────────────────────────
    extracted_intents = state.get("extracted_intents", [])
    regex_intent = state.get("regex_intent", "GENERAL")
    primary_intent = extracted_intents[0] if extracted_intents else regex_intent

    node_path = state.get("node_transitions", [])
    is_multi_intent = len(extracted_intents) > 1
    workflow_type = "MULTI_INTENT" if is_multi_intent else primary_intent

    # ── Build WorkflowSummary ─────────────────────────────────────────────
    plan = state.get("workflow_plan", [])
    workflow_summary = WorkflowSummary(
        intent=primary_intent,
        workflow_type=workflow_type,
        steps_planned=len(plan),
        steps_completed=len(state.get("completed_steps", [])),
        steps_failed=len(state.get("failed_steps", [])),
        steps_skipped=len(state.get("skipped_steps", [])),
        escalation_triggered=state.get("escalation_required", False),
        node_path=node_path,
        channel=state.get("channel", "chat"),
    )

    # ── Build enriched TraceInfo ──────────────────────────────────────────
    trace_info = TraceInfo(
        trace_id=trace_id,
        session_id=session_id,
        latency_ms=total_latency_ms,
        tool_calls=tool_call_infos,
        node_spans=node_spans,
        workflow_summary=workflow_summary,
        retry_counts=state.get("retry_counts", {}),
        policy_violations=state.get("policy_violations", []),
    )

    # ── Commit to in-memory trace store ───────────────────────────────────
    _trace_store[trace_id] = trace_info.model_dump()

    # ── Emit structured observability log ─────────────────────────────────
    logger.info(
        "Workflow completed",
        trace_id=trace_id,
        session_id=session_id,
        latency_ms=total_latency_ms,
        intent=primary_intent,
        workflow_type=workflow_type,
        steps_planned=len(plan),
        steps_completed=len(state.get("completed_steps", [])),
        steps_failed=len(state.get("failed_steps", [])),
        steps_skipped=len(state.get("skipped_steps", [])),
        escalation_triggered=state.get("escalation_required", False),
        tool_call_count=len(tool_call_infos),
        retry_counts=state.get("retry_counts", {}),
        policy_violations=len(state.get("policy_violations", [])),
        node_path=node_path,
        # Per-node latency breakdown
        **{f"latency_{k}_ms": v for k, v in node_latencies.items()},
    )

    # Extension point: Prometheus metrics push
    # metrics.workflow_duration.observe(total_latency_ms / 1000)
    # metrics.escalation_total.inc() if escalation_required

    # Extension point: OpenTelemetry span export
    # otel_tracer.start_span(trace_id, attributes={...})

    existing_latencies = dict(state.get("node_latencies", {}))
    existing_latencies["trace_finalizer"] = _ms_since(t0)

    existing_transitions = list(state.get("node_transitions", []))
    existing_transitions.append("trace_finalizer")

    return {
        "node_latencies": existing_latencies,
        "node_transitions": existing_transitions,
    }
