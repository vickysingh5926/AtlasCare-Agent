"""
Regex Router Node — Fast-Path Deterministic Intent Classification

This is the FIRST node in every workflow execution. It runs the existing
regex-based intent classifier synchronously (no LLM call, no I/O) to:
  1. Classify the primary intent (TRACKING | COMPOUND | ESCALATION | POLICY | GENERAL)
  2. Extract structured entities (order_id, amount, item_index, new_address)
  3. Record per-node latency for observability

Routing output:
  - TRACKING (with no conditional clauses) → policy_validation (fast path, skip LLM)
  - Everything else → structured_extraction (LLM enrichment)

This node NEVER calls an LLM. It is the deterministic fast-path gateway.
"""

import re
import time
from typing import Any, Dict

from agent.intent import classify_intent, extract_entities
from agent.state import AgentState
from utils.logger import logger
from utils.tracing import utcnow


def _ms_since(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)


async def regex_router_node(state: AgentState) -> Dict[str, Any]:
    """
    Fast-path regex intent classification and entity extraction.

    Wraps the existing deterministic classify_intent() and extract_entities()
    functions from agent/intent.py. No behavioural change from the original
    ReAct loop — this node just makes the classification explicit in the graph.

    Returns:
        Partial AgentState with:
        - regex_intent: classified intent string
        - detected_entities: extracted entity dict
        - order_ids: list of referenced order IDs
        - refund_amount: extracted refund amount (or None)
        - item_indices: extracted item indices
        - new_address: extracted shipping address (or None)
        - node_latencies: updated with this node's latency
        - node_transitions: updated with "regex_router"
    """
    t0 = time.perf_counter()
    message = state.get("sanitized_message", state.get("user_message", ""))

    intent = classify_intent(message)
    entities = extract_entities(message)

    logger.info(
        "Regex router completed",
        trace_id=state.get("trace_id"),
        intent=intent.value,
        entities=entities,
    )

    # Build order_ids list
    order_ids = [entities["order_id"]] if entities.get("order_id") else []

    # Parse refund amount — enhanced extraction
    # First try the generic entity extractor; if it returns None, use a targeted
    # 'refund [me] NUMBER' pattern to avoid re.search picking up small digits
    # in order IDs (e.g. '3' from ORD-J3) before the actual amount.
    refund_amount = None
    if entities.get("amount"):
        try:
            refund_amount = float(entities["amount"])
        except (ValueError, TypeError):
            pass

    if refund_amount is None:
        # Targeted fallback: look for amounts near refund/reimburse keywords
        refund_match = re.search(
            r'\b(?:refund|reimburse)\b[^\d]*(?:Rs\.?\s*|\u20b9\s*|INR\s*)?(\d[\d,]{2,})\b',
            message,
            re.IGNORECASE,
        )
        if refund_match:
            try:
                val = float(refund_match.group(1).replace(',', ''))
                if val >= 100:
                    refund_amount = val
            except (ValueError, TypeError):
                pass

    # Parse item indices
    item_indices = []
    if entities.get("item_index"):
        try:
            item_indices = [int(entities["item_index"])]
        except (ValueError, TypeError):
            pass

    latency = _ms_since(t0)
    existing_latencies = dict(state.get("node_latencies", {}))
    existing_latencies["regex_router"] = latency

    existing_transitions = list(state.get("node_transitions", []))
    existing_transitions.append("regex_router")

    return {
        "regex_intent": intent.value,
        "detected_entities": entities,
        "order_ids": order_ids,
        "refund_amount": refund_amount,
        "item_indices": item_indices,
        "new_address": entities.get("new_address"),
        "node_latencies": existing_latencies,
        "node_transitions": existing_transitions,
    }
