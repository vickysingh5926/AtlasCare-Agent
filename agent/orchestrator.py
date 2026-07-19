"""
Agent Orchestrator — Thin LangGraph Adapter

This module is now a thin adapter between the FastAPI layer and the
LangGraph workflow graph. It:
  1. Initialises AgentState from the incoming request
  2. Invokes the compiled graph via graph.ainvoke()
  3. Converts the final AgentState into the QueryResponse API contract
  4. Provides get_trace() for the GET /trace/{trace_id} endpoint

The orchestration logic (ReAct loop, guardrails, tool dispatch) has moved
into dedicated graph nodes in agent/nodes/. The API contract is unchanged.

Trace store:
  - Written by: agent/nodes/trace_finalizer.py
  - Read by: get_trace() (below) for GET /trace/{id}
  - Shared via: agent._trace_store (module-level dict)
  - Production: replace with Redis client for multi-worker consistency
"""

import time
import time as _time
from typing import Any, Dict, Optional

from agent.state import AgentState
from agent.graph import get_graph
from agent import _trace_store
from models.schemas import QueryResponse, TraceInfo, ToolCallInfo
from utils.tracing import generate_trace_id, utcnow
from utils.logger import logger


def get_trace(trace_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve a stored interaction trace by trace_id.

    Used by the GET /trace/{trace_id} endpoint in main.py.
    The trace is written by trace_finalizer_node after each workflow completes.

    Returns None if trace_id is not found.
    """
    return _trace_store.get(trace_id)


async def handle_query(
    message: str, session_id: str, customer_id: str
) -> QueryResponse:
    """
    Main entry point for processing customer queries.

    Thin adapter: builds AgentState, invokes the LangGraph workflow graph,
    and converts the final state into QueryResponse.

    Preserves the exact API contract:
      Response: {response: str, trace: {trace_id, session_id, latency_ms, tool_calls}}

    Args:
        message: Sanitized customer query text (sanitized by main.py before here).
        session_id: Client-provided session identifier.
        customer_id: Customer identifier for CRM operations.

    Returns:
        QueryResponse with agent response text and full enriched trace.
    """
    trace_id = generate_trace_id()
    start_ns = time.monotonic_ns()
    start_perf = time.perf_counter()

    logger.info(
        "Query received — invoking LangGraph workflow",
        trace_id=trace_id,
        session_id=session_id,
        customer_id=customer_id,
    )

    # ── Initialise AgentState ─────────────────────────────────────────────
    initial_state = AgentState(
        # Identity
        session_id=session_id,
        trace_id=trace_id,
        customer_id=customer_id,
        channel="chat",

        # Input
        user_message=message,
        sanitized_message=message,  # Already sanitized by main.py

        # Intent (populated by regex_router_node)
        regex_intent="",
        extracted_intents=[],
        detected_entities={},
        order_ids=[],
        refund_amount=None,
        item_indices=[],
        new_address=None,
        conditions=[],
        actions=[],

        # Governance
        policy_violations=[],
        escalation_required=False,
        escalation_reason="",

        # Execution plan
        workflow_plan=[],
        current_step=0,

        # Results
        tool_results=[],
        completed_steps=[],
        failed_steps=[],
        skipped_steps=[],

        # Idempotency
        executed_ops=[],

        # Observability
        node_latencies={},
        node_transitions=[],
        retry_counts={},
        start_time_ns=start_ns,

        # Output
        final_response="",
        error_message="",
        workflow_complete=False,
    )

    # ── Invoke LangGraph graph ────────────────────────────────────────────
    try:
        graph = get_graph()
        final_state: AgentState = await graph.ainvoke(initial_state)
    except Exception as exc:
        # Unrecoverable graph error — return safe fallback response
        latency = int((time.perf_counter() - start_perf) * 1000)
        logger.error(
            "LangGraph invocation failed — returning fallback response",
            trace_id=trace_id,
            error=str(exc),
            error_type=type(exc).__name__,
            latency_ms=latency,
        )
        return _build_error_response(trace_id, session_id, latency, str(exc))

    # ── Extract outputs from final state ──────────────────────────────────
    latency = int((time.perf_counter() - start_perf) * 1000)

    final_response = final_state.get("final_response") or (
        "I have processed your request. Please check your account for updates."
    )

    # Convert internal ToolCallRecords to public ToolCallInfo models.
    # Filter out guardrail-blocked records for tools that were NEVER dispatched
    # (e.g. payments blocked by the ₹25K refund limit). These records exist in
    # internal state for audit, but the API contract expects that a blocked tool
    # "does not appear in trace" — because it was never actually invoked.
    tool_calls = [
        ToolCallInfo(
            tool=tr.get("tool", "unknown"),
            params=tr.get("params", {}),
            result=tr.get("result", "unknown"),
            data=tr.get("data"),
            timestamp=tr.get("timestamp", utcnow()),
        )
        for tr in final_state.get("tool_results", [])
        if tr.get("result") != "blocked"
    ]

    logger.info(
        "Query completed via LangGraph",
        trace_id=trace_id,
        session_id=session_id,
        latency_ms=latency,
        tool_calls=len(tool_calls),
        escalation=final_state.get("escalation_required", False),
        node_path=final_state.get("node_transitions", []),
    )

    # ── Build TraceInfo (enriched, backward-compatible) ───────────────────
    # The trace was already written to _trace_store by trace_finalizer_node.
    # We reconstruct it here for the QueryResponse return value.
    stored = _trace_store.get(trace_id, {})

    trace = TraceInfo(
        trace_id=trace_id,
        session_id=session_id,
        latency_ms=latency,
        tool_calls=tool_calls,
        retry_counts=final_state.get("retry_counts", {}),
        policy_violations=final_state.get("policy_violations", []),
    )

    return QueryResponse(
        response=final_response,
        trace=trace,
    )


def _build_error_response(
    trace_id: str, session_id: str, latency: int, error: str
) -> QueryResponse:
    """Build a safe fallback QueryResponse for unrecoverable errors."""
    return QueryResponse(
        response=(
            "I'm having trouble processing your request right now. "
            "Please try again or contact our support team."
        ),
        trace=TraceInfo(
            trace_id=trace_id,
            session_id=session_id,
            latency_ms=latency,
            tool_calls=[],
            policy_violations=[f"Internal error: {error}"],
        ),
    )
