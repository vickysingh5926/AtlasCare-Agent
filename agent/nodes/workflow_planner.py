"""
Workflow Planner Node — Deterministic Execution Plan Generation

This node converts the extracted intents and entities into a strongly-typed,
ordered list of WorkflowSteps with explicit dependency relationships.

Critically: the plan is generated DETERMINISTICALLY — not by the LLM.
The LLM (in structured_extraction_node) extracted WHAT the customer wants.
This node translates that into HOW to execute it, following fixed business rules:

  Rule 1: cancel_item MUST precede initiate_refund (causal dependency)
  Rule 2: update_address is independent (no dependencies)
  Rule 3: track_order is independent (no dependencies)
  Rule 4: lookup_policy is independent (no dependencies)

If policy_validation flagged escalation_required=True for refund, the refund
step is still added to the plan with a note — the executor will skip it
via the pre-execution guardrail. This preserves the audit record of intent.

This node wraps and extends the logic in agent/planner.py.
"""

import re
import time
from typing import Any, Dict, List, Optional

from agent.state import AgentState, WorkflowStep
from agent.intent import Intent
from utils.logger import logger


def _ms_since(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)


def _build_policy_query(raw_message: str) -> str:
    """
    Build a clean policy-focused search query from the raw user message.

    Strips order IDs, currency amounts, and common filler phrases that
    would add noise to the KB keyword search. Falls back to the original
    message if cleaning produces an empty string.

    Examples:
        "What is the return policy for ORD-J1?" → "return policy"
        "Track ORD-J1 and tell me the refund policy" → "refund policy"
        "Can I return a damaged item worth Rs.15000?" → "return damaged item"
    """
    cleaned = raw_message

    # Strip order IDs (ORD-J1, ORD-78321, etc.)
    cleaned = re.sub(r'\bORD-\w+\b', '', cleaned, flags=re.IGNORECASE)

    # Strip currency amounts (Rs.25000, Rs. 25,000, INR 15000, ₹5000, etc.)
    cleaned = re.sub(r'(?:Rs\.?\s*|INR\s*|₹\s*)\d[\d,]*', '', cleaned, flags=re.IGNORECASE)

    # Strip bare large numbers that look like amounts (>= 100)
    cleaned = re.sub(r'\b\d{3,}[\d,]*\b', '', cleaned)

    # Strip common filler phrases that don't help search
    filler_patterns = [
        r'\bfor\s+my\s+order\b',
        r'\bfrom\s+my\s+order\b',
        r'\bplease\b',
        r'\btell\s+me\b',
        r'\blet\s+me\s+know\b',
        r'\bi\s+want\s+to\s+know\b',
        r'\bcan\s+you\b',
        r'\bcould\s+you\b',
        r'\balso\b',
        r'\band\b',
    ]
    for pattern in filler_patterns:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)

    # Collapse whitespace and strip
    cleaned = re.sub(r'\s+', ' ', cleaned).strip().strip('.,;:?!')

    # Fall back to original if cleaning was too aggressive
    return cleaned if len(cleaned) > 3 else raw_message


async def workflow_planner_node(state: AgentState) -> Dict[str, Any]:
    """
    Generate an ordered, dependency-aware execution plan.

    Reads:
      - extracted_intents, actions (from structured_extraction_node)
      - order_ids, refund_amount, item_indices, new_address (entities)
      - escalation_required (from policy_validation_node)

    Produces:
      - workflow_plan: List[WorkflowStep] with explicit step ordering
        and dependency declarations

    Returns:
        Partial AgentState with workflow_plan set.
    """
    t0 = time.perf_counter()
    trace_id = state.get("trace_id", "")

    # Resolve primary intent for routing
    extracted_intents = state.get("extracted_intents", [])
    regex_intent = state.get("regex_intent", "GENERAL")
    primary_intent = extracted_intents[0] if extracted_intents else regex_intent

    # Entity resolution
    order_ids = state.get("order_ids", [])
    order_id = order_ids[0] if order_ids else None
    refund_amount = state.get("refund_amount")
    item_indices = state.get("item_indices", [])
    item_index = item_indices[0] if item_indices else None
    new_address = state.get("new_address")
    customer_id = state.get("customer_id", "CUST-001")
    actions = state.get("actions", [])

    plan: List[WorkflowStep] = []
    step = 1

    # ── TRACKING ─────────────────────────────────────────────────────────
    # Also detect tracking signals in raw message for mixed queries
    raw_msg_lower = state.get("sanitized_message", "").lower()
    has_tracking_signal = bool(
        re.search(r'\b(track|where\s+is|status\s+of|delivery\s+status)\b', raw_msg_lower)
        and re.search(r'\bORD-\w+\b', state.get("sanitized_message", ""), re.IGNORECASE)
    )
    if primary_intent == Intent.TRACKING.value or "track_order" in actions or has_tracking_signal:
        if order_id:
            plan.append(WorkflowStep(
                step=step,
                tool="oms",
                operation="get_order_status",
                params={"operation": "get_order_status", "order_id": order_id},
                depends_on=[],
            ))
            step += 1

    # ── CANCEL LINE ITEM ──────────────────────────────────────────────────
    # Must happen BEFORE refund (step number recorded for dependency)
    cancel_step_num: Optional[int] = None
    if (
        primary_intent in (Intent.COMPOUND.value, Intent.ESCALATION.value)
        or "cancel_item" in actions
    ) and order_id:
        idx = item_index if item_index else 1
        plan.append(WorkflowStep(
            step=step,
            tool="oms",
            operation="cancel_line_item",
            params={
                "operation": "cancel_line_item",
                "order_id": order_id,
                "item_index": idx,
            },
            depends_on=[],
        ))
        cancel_step_num = step
        step += 1

    # ── REFUND ───────────────────────────────────────────────────────────
    # Depends on cancel if both are present; the executor guardrail will
    # block this if amount > REFUND_AUTO_LIMIT.
    if (
        refund_amount is not None
        and order_id
        and ("initiate_refund" in actions or refund_amount > 0)
    ):
        deps = [cancel_step_num] if cancel_step_num else []
        plan.append(WorkflowStep(
            step=step,
            tool="payments",
            operation="initiate_refund",
            params={
                "operation": "initiate_refund",
                "order_id": order_id,
                "amount": refund_amount,
            },
            depends_on=deps,
        ))
        step += 1

    # ── ADDRESS UPDATE ────────────────────────────────────────────────────
    if new_address and order_id:
        plan.append(WorkflowStep(
            step=step,
            tool="oms",
            operation="update_shipping_address",
            params={
                "operation": "update_shipping_address",
                "order_id": order_id,
                "new_address": new_address,
            },
            depends_on=[],
        ))
        step += 1

    # ── POLICY LOOKUP ─────────────────────────────────────────────────────
    # Triggers when:
    #   1. Primary intent is POLICY, OR
    #   2. LLM extracted "lookup_policy" action, OR
    #   3. Policy-related keywords are detected in the raw message
    #      (handles mixed queries like "track ORD-X and what is the return policy")
    raw_message = state.get("sanitized_message", "")
    raw_lower = raw_message.lower()
    has_policy_signal = bool(
        re.search(r'\b(policy|policies)\b', raw_lower)
        or re.search(r'\b(return|refund|exchange|warranty|shipping)\b.*\b(rules?|window|period|days)\b', raw_lower)
        or re.search(r'\bwhat\s+(is|are)\b.*\b(return|refund|shipping|warranty|exchange|cancellation)\b', raw_lower)
        or re.search(r'\bhow\s+(long|many\s+days)\b.*\b(return|refund|exchange|shipping|deliver)\b', raw_lower)
        or re.search(r'\b(eligible|eligib|faq|guarantee)\b', raw_lower)
        or re.search(r'\b(damaged|broken|defective|faulty)\b.*\b(item|product|order)\b', raw_lower)
        or re.search(r'\bmoney\s+back\b', raw_lower)
        or re.search(r'\bwarrant', raw_lower)
    )

    if primary_intent == Intent.POLICY.value or "lookup_policy" in actions or has_policy_signal:
        clean_query = _build_policy_query(raw_message)
        plan.append(WorkflowStep(
            step=step,
            tool="kb",
            operation="search_policy",
            params={"operation": "search_policy", "query": clean_query},
            depends_on=[],
        ))
        step += 1

    # ── GENERAL (no structured plan available) ────────────────────────────
    # The response_generator_node will handle this via direct LLM synthesis.
    if not plan:
        logger.info(
            "No structured plan generated — will use LLM response synthesis",
            trace_id=trace_id,
            intent=primary_intent,
        )

    latency = _ms_since(t0)
    existing_latencies = dict(state.get("node_latencies", {}))
    existing_latencies["workflow_planner"] = latency

    existing_transitions = list(state.get("node_transitions", []))
    existing_transitions.append("workflow_planner")

    logger.info(
        "Workflow plan generated",
        trace_id=trace_id,
        intent=primary_intent,
        steps=len(plan),
        plan=[{"step": s["step"], "tool": s["tool"], "op": s["operation"]} for s in plan],
        latency_ms=latency,
    )

    return {
        "workflow_plan": plan,
        "current_step": 0,
        "node_latencies": existing_latencies,
        "node_transitions": existing_transitions,
    }
