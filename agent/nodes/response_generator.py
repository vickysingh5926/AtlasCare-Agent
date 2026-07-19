"""
Response Generator Node — Grounded LLM Text Synthesis

This is the SECOND and LAST LLM call in the entire workflow.

The LLM in this node:
  - READS tool results from state["tool_results"] → generates human text
  - CANNOT trigger tools (no tool schemas are passed to the LLM call)
  - CANNOT make policy decisions (all decisions already made upstream)
  - CANNOT see the original user message in a way that triggers re-planning

Post-generation: the existing hallucination grounding check is applied
to ensure the LLM only references values that actually appear in tool results.

Fallback: if the LLM is unavailable, a deterministic summary is built
directly from tool_results without any LLM involvement.
"""

import json
import time
from typing import Any, Dict, List, Optional

from agent.state import AgentState, ToolCallRecord
from agent.prompts import RESPONSE_SYNTHESIS_PROMPT
from guardrails.hallucination import check_response_grounding
from utils.llm_client import chat, MODEL_FAST
from utils.logger import logger


def _ms_since(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)


async def response_generator_node(state: AgentState) -> Dict[str, Any]:
    """
    Synthesise the final customer-facing response.

    Builds a grounding context from tool_results and asks the LLM to
    write a concise, accurate response. Falls back to a deterministic
    summary if the LLM call fails.

    The LLM receives:
      - A synthesis-only system prompt (no tool schemas)
      - A structured summary of all tool outcomes
      - The original customer query (for context only, no re-planning)

    Returns:
        Partial AgentState with final_response, workflow_complete=True.
    """
    t0 = time.perf_counter()
    trace_id = state.get("trace_id", "")
    message = state.get("sanitized_message", state.get("user_message", ""))
    tool_results: List[ToolCallRecord] = state.get("tool_results", [])
    escalation_required = state.get("escalation_required", False)
    escalation_reason = state.get("escalation_reason", "")

    # Build grounding context from tool results
    grounding_context = _build_grounding_context(tool_results, escalation_required, escalation_reason)

    # Attempt LLM synthesis
    final_response: Optional[str] = None
    try:
        final_response = await _synthesise_with_llm(message, grounding_context, trace_id)
    except Exception as exc:
        logger.warning(
            "Response synthesis LLM failed — using deterministic fallback",
            trace_id=trace_id,
            error=str(exc),
        )

    if not final_response:
        # Deterministic fallback: build response directly from tool_results
        final_response = _build_deterministic_response(
            tool_results, escalation_required, escalation_reason
        )
        logger.info("Using deterministic response fallback", trace_id=trace_id)

    # Hallucination grounding check (post-generation)
    tool_data = [tr.get("data") for tr in tool_results if tr.get("data")]
    grounding = check_response_grounding(final_response, tool_data)
    if not grounding["grounded"]:
        logger.warning(
            "Response grounding check failed",
            trace_id=trace_id,
            suspicious=grounding["suspicious_tokens"],
        )

    latency = _ms_since(t0)
    existing_latencies = dict(state.get("node_latencies", {}))
    existing_latencies["response_generator"] = latency

    existing_transitions = list(state.get("node_transitions", []))
    existing_transitions.append("response_generator")

    logger.info(
        "Response generated",
        trace_id=trace_id,
        grounded=grounding["grounded"],
        latency_ms=latency,
    )

    return {
        "final_response": final_response,
        "workflow_complete": True,
        "node_latencies": existing_latencies,
        "node_transitions": existing_transitions,
    }


async def _synthesise_with_llm(
    user_message: str,
    grounding_context: str,
    trace_id: str,
) -> str:
    """
    Call Groq LLM for response synthesis.

    NO tool schemas are passed — the LLM cannot trigger tools.
    The grounding_context provides all factual data the LLM may reference.
    """
    messages = [
        {"role": "system", "content": RESPONSE_SYNTHESIS_PROMPT},
        {
            "role": "user",
            "content": (
                f"Customer query: {user_message}\n\n"
                f"Actions taken and results:\n{grounding_context}"
            ),
        },
    ]

    response = await chat(messages, tools=None, model=MODEL_FAST)  # Fast model for synthesis
    return (response.text or "").strip()


def _build_grounding_context(
    tool_results: List[ToolCallRecord],
    escalation_required: bool,
    escalation_reason: str,
) -> str:
    """
    Build a structured text summary of all tool outcomes for LLM grounding.

    This is the ONLY source of factual data the LLM may reference in its
    response. By making tool data explicit, we reduce hallucination risk.

    For KB/policy results, the actual article content is included so the
    LLM can synthesise accurate policy answers grounded in real data.
    """
    lines = []
    for tr in tool_results:
        tool = tr.get("tool", "unknown")
        operation = tr.get("operation", "unknown")
        result = tr.get("result", "unknown")
        data = tr.get("data", {}) or {}

        if result == "success":
            msg = data.get("message", f"{tool}.{operation} succeeded")
            lines.append(f"✓ {tool}.{operation}: {msg}")

            # Include structured data for tracking queries
            if tool == "oms" and operation == "get_order_status" and "data" in data:
                order_data = data["data"]
                lines.append(f"  Order status: {order_data.get('status', 'unknown')}")
                lines.append(f"  Tracking: {order_data.get('tracking_number', 'N/A')}")
                lines.append(f"  Estimated delivery: {order_data.get('estimated_delivery', 'N/A')}")

            # Include actual KB article content for policy queries
            if tool == "kb" and operation == "search_policy" and "data" in data:
                articles = data["data"]
                if isinstance(articles, list):
                    for i, article in enumerate(articles[:3], 1):
                        title = article.get("title", "Untitled")
                        content = article.get("content", "")
                        lines.append(f"  Article {i}: \"{title}\"")
                        if content:
                            lines.append(f"  Content: {content}")

        elif result == "blocked":
            reason = data.get("reason", "Operation blocked by policy")
            lines.append(f"✗ {tool}.{operation}: BLOCKED — {reason}")
        elif result == "skipped":
            reason = data.get("reason", "Skipped")
            lines.append(f"– {tool}.{operation}: SKIPPED — {reason}")
        elif result == "error":
            msg = data.get("message", f"{tool}.{operation} failed")
            lines.append(f"✗ {tool}.{operation}: ERROR — {msg}")
        elif tool == "crm" and operation == "create_case":
            case_id = data.get("case_id", "CASE-UNKNOWN")
            lines.append(f"✓ CRM case created: {case_id}")

    if escalation_required and escalation_reason:
        lines.append(f"\nEscalation required: {escalation_reason}")

    return "\n".join(lines) if lines else "No actions were taken."


def _build_deterministic_response(
    tool_results: List[ToolCallRecord],
    escalation_required: bool,
    escalation_reason: str,
) -> str:
    """
    Build a deterministic response without LLM involvement.

    Used as fallback when Groq LLM is unavailable.
    Handles all journey types:
      - Tracking: reports order status from OMS data
      - Compound/Escalation: summarises completed actions + escalation
      - Policy: includes actual article content from KB results
    """
    successes = []
    kb_articles = []

    for tr in tool_results:
        if tr.get("result") != "success" or tr.get("tool") == "crm":
            continue
        data = tr.get("data") or {}

        # KB results: extract actual article content for policy queries
        if tr.get("tool") == "kb" and tr.get("operation") == "search_policy":
            articles = data.get("data", [])
            if isinstance(articles, list):
                for article in articles[:3]:  # Top 3 articles
                    title = article.get("title", "")
                    content = article.get("content", "")
                    if title or content:
                        kb_articles.append(f"**{title}**: {content}" if title else content)
            if not kb_articles:
                successes.append(data.get("message", "Policy lookup completed"))
        else:
            msg = data.get("message", "")
            if msg:
                successes.append(msg)

    crm_calls = [tr for tr in tool_results if tr.get("tool") == "crm"]
    case_id = (
        crm_calls[-1]["data"].get("case_id", "CASE-PENDING")
        if crm_calls and crm_calls[-1].get("data")
        else "CASE-PENDING"
    )

    parts = []

    # KB/Policy response
    if kb_articles:
        parts.append(
            "Here is the relevant policy information:\n"
            + "\n".join(f"- {a}" for a in kb_articles)
        )

    if successes:
        parts.append("Here's what I've done:\n" + "\n".join(f"- {s}" for s in successes if s))

    if escalation_required and escalation_reason:
        parts.append(
            f"Regarding the refund: {escalation_reason}. "
            f"I've created support case {case_id} for a human agent to review. "
            "You'll be contacted shortly."
        )
    elif not parts:
        parts.append(
            "I've processed your request. Please check your account for updates."
        )

    return "\n\n".join(parts)
