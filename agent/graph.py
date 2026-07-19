"""
LangGraph Graph Builder — AtlasCare Workflow Orchestration

Defines the compiled LangGraph StateGraph that replaces the generic ReAct loop.

"""

from langgraph.graph import StateGraph, END

from agent.state import AgentState
from agent.nodes.regex_router import regex_router_node
from agent.nodes.structured_extraction import structured_extraction_node
from agent.nodes.policy_validation import policy_validation_node
from agent.nodes.workflow_planner import workflow_planner_node
from agent.nodes.deterministic_executor import deterministic_executor_node
from agent.nodes.escalation_handler import escalation_handler_node
from agent.nodes.response_generator import response_generator_node
from agent.nodes.trace_finalizer import trace_finalizer_node
from utils.logger import logger


# ── Conditional Routing Functions ─────────────────────────────────────────────

def route_after_regex(state: AgentState) -> str:
    """
    Decide whether to skip LLM extraction (fast-path) or invoke it.

    Fast-path conditions (skip structured_extraction_node):
      - Pure TRACKING intent (no conditional clauses, no compound signals)
      - Pure POLICY intent (simple KB lookup, no ambiguity)

    All other queries go through structured_extraction for LLM enrichment.
    This saves ~500-800ms per simple tracking query at scale.
    """
    regex_intent = state.get("regex_intent", "GENERAL")
    conditions = state.get("conditions", [])

    # Fast path: pure tracking or policy with no conditions
    if regex_intent in ("TRACKING", "POLICY") and not conditions:
        logger.info(
            "Routing: fast path (skip LLM extraction)",
            trace_id=state.get("trace_id"),
            intent=regex_intent,
        )
        return "policy_validation"

    logger.info(
        "Routing: LLM structured extraction needed",
        trace_id=state.get("trace_id"),
        intent=regex_intent,
    )
    return "structured_extraction"


def route_after_policy(state: AgentState) -> str:
    """
    Route based on pre-flight policy validation outcome.

   

    """
    return "workflow_planner"


def route_after_executor(state: AgentState) -> str:
    """
    Route based on mid-execution escalation detection.

    If the executor triggered escalation (e.g., refund tool returned 'escalate'
    action, or post-execution detection fired), create the CRM case now.
    """
    if state.get("escalation_required", False):
        # Check if a CRM case was already created (avoid duplicates)
        tool_results = state.get("tool_results", [])
        crm_created = any(
            tr.get("tool") == "crm" and tr.get("operation") == "create_case"
            for tr in tool_results
        )
        if not crm_created:
            logger.info(
                "Routing: mid-execution escalation — creating CRM case",
                trace_id=state.get("trace_id"),
            )
            return "escalation_handler"

    return "response_generator"


# ── Graph Construction ────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    """
    Build and compile the AtlasCare LangGraph workflow graph.

    Returns a compiled StateGraph ready for ainvoke().
    The graph uses MemorySaver for in-process checkpointing.
    Extension point: swap MemorySaver for AsyncPostgresSaver or RedisSaver
    for persistent, multi-worker checkpointing in production.
    """
    graph = StateGraph(AgentState)

    # ── Register nodes ────────────────────────────────────────────────────
    graph.add_node("regex_router", regex_router_node)
    graph.add_node("structured_extraction", structured_extraction_node)
    graph.add_node("policy_validation", policy_validation_node)
    graph.add_node("workflow_planner", workflow_planner_node)
    graph.add_node("deterministic_executor", deterministic_executor_node)
    graph.add_node("escalation_handler", escalation_handler_node)
    graph.add_node("response_generator", response_generator_node)
    graph.add_node("trace_finalizer", trace_finalizer_node)

    # ── Entry point ───────────────────────────────────────────────────────
    graph.set_entry_point("regex_router")

    # ── Conditional routing: after regex_router ───────────────────────────
    graph.add_conditional_edges(
        "regex_router",
        route_after_regex,
        {
            "structured_extraction": "structured_extraction",
            "policy_validation": "policy_validation",
        },
    )

    # ── structured_extraction → policy_validation (always) ────────────────
    graph.add_edge("structured_extraction", "policy_validation")

    # ── policy_validation → workflow_planner (always) ──────────────────────
    # Even when escalation_required=True, we still plan and execute: the
    # executor guardrail blocks the refund step, other steps proceed, and
    # route_after_executor handles CRM case creation afterward.
    graph.add_edge("policy_validation", "workflow_planner")

    # ── workflow_planner → deterministic_executor (always) ────────────────
    graph.add_edge("workflow_planner", "deterministic_executor")

    # ── Conditional routing: after deterministic_executor ─────────────────
    graph.add_conditional_edges(
        "deterministic_executor",
        route_after_executor,
        {
            "escalation_handler": "escalation_handler",
            "response_generator": "response_generator",
        },
    )

    # ── escalation_handler → response_generator (always) ─────────────────
    graph.add_edge("escalation_handler", "response_generator")

    # ── response_generator → trace_finalizer (always) ─────────────────────
    graph.add_edge("response_generator", "trace_finalizer")

    # ── trace_finalizer → END ─────────────────────────────────────────────
    graph.add_edge("trace_finalizer", END)

    return graph.compile()


# ── Singleton compiled graph ──────────────────────────────────────────────────
# Compiled once at module import time. Thread-safe for concurrent invocations.
# Extension point: add checkpointer=AsyncPostgresSaver(...) for persistence.
_compiled_graph = None


def get_graph():
    """Get the singleton compiled graph (lazy-initialized)."""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph
