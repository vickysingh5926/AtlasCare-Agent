"""
Structured Extraction Node — LLM-Powered Intent and Entity Understanding

This node handles queries that the fast-path regex classifier cannot fully
resolve: compound requests, conditional instructions, mixed intents, and
semantically complex queries.

Responsibilities:
  - Call Groq LLM with a strict structured output schema (IntentExtraction)
  - Extract multiple intents, entities, conditions, and action sequences
  - Fall back to regex-derived state on LLM failure (safe degradation)

Governance constraints:
  - The LLM ONLY extracts WHAT the customer wants (intents + entities)
  - The LLM NEVER decides WHAT TO DO (no tool calls, no policy decisions)
  - All governance happens downstream in policy_validation_node
  - All tool dispatch happens in deterministic_executor_node

Example stress-test queries this node handles:
  "Track my order and cancel item 2 if not shipped"
  "Refund item 3 and change delivery address"
  "Cancel item 2 but only if refund goes to my HDFC card"
  "Where is my package and why was I charged twice?"
"""

import json
import time
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from agent.state import AgentState
from agent.prompts import EXTRACTION_PROMPT
from utils.llm_client import chat
from utils.logger import logger


def _ms_since(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)


# ── Strict Pydantic schema for LLM structured output ─────────────────────────

class IntentExtraction(BaseModel):
    """
    Strict structured output schema for LLM intent extraction.

    The LLM is constrained to populate ONLY these fields.
    It makes NO policy decisions and generates NO tool call sequences.
    """
    intents: List[str] = Field(
        default_factory=list,
        description="List of detected intents: TRACKING | COMPOUND | ESCALATION | POLICY | GENERAL",
    )
    order_ids: List[str] = Field(
        default_factory=list,
        description="All order IDs referenced (e.g. ORD-J1, ORD-12345)",
    )
    refund_amount: Optional[float] = Field(
        default=None,
        description="Refund amount in INR, if mentioned",
    )
    item_indices: List[int] = Field(
        default_factory=list,
        description="Line item indices referenced (1-based)",
    )
    new_address: Optional[str] = Field(
        default=None,
        description="New shipping address if an address update is requested",
    )
    conditions: List[str] = Field(
        default_factory=list,
        description="Conditional clauses: e.g. 'only if not shipped', 'only if HDFC card'",
    )
    actions: List[str] = Field(
        default_factory=list,
        description="Requested actions: cancel_item | initiate_refund | update_address | track_order | lookup_policy",
    )
    escalation_required: bool = Field(
        default=False,
        description="True only if customer EXPLICITLY requests human escalation",
    )


async def structured_extraction_node(state: AgentState) -> Dict[str, Any]:
    """
    LLM-powered structured extraction for complex/ambiguous queries.

    Uses Groq (Llama 3.3 70B) to populate IntentExtraction via a constrained JSON prompt.
    On any LLM failure (timeout, bad JSON, API error), falls back to the
    regex-derived state already set by regex_router_node — ensuring the
    workflow always continues safely.

    The LLM call in this node is the ONLY place in the entire pipeline where
    the LLM is given the user message for semantic understanding. It cannot
    trigger tool calls from here.

    Returns:
        Partial AgentState with enriched intent and entity fields.
    """
    t0 = time.perf_counter()
    message = state.get("sanitized_message", state.get("user_message", ""))
    trace_id = state.get("trace_id", "")

    logger.info(
        "Structured extraction started",
        trace_id=trace_id,
        regex_intent=state.get("regex_intent"),
    )

    extraction: Optional[IntentExtraction] = None

    try:
        extraction = await _extract_with_llm(message, trace_id)
    except Exception as exc:
        logger.warning(
            "Structured extraction LLM call failed — falling back to regex",
            trace_id=trace_id,
            error=str(exc),
        )

    latency = _ms_since(t0)
    existing_latencies = dict(state.get("node_latencies", {}))
    existing_latencies["structured_extraction"] = latency

    existing_transitions = list(state.get("node_transitions", []))
    existing_transitions.append("structured_extraction")

    if extraction is None:
        # Graceful fallback: use regex-derived state
        logger.info(
            "Using regex fallback for extraction",
            trace_id=trace_id,
        )
        regex_intent = state.get("regex_intent", "GENERAL")
        return {
            "extracted_intents": [regex_intent] if regex_intent else ["GENERAL"],
            "conditions": [],
            "actions": [],
            "node_latencies": existing_latencies,
            "node_transitions": existing_transitions,
        }

    # Merge LLM extraction with regex results (LLM enriches, regex provides baseline)
    extracted_intents = extraction.intents if extraction.intents else [state.get("regex_intent", "GENERAL")]

    # LLM entity values take precedence; fall back to regex if LLM returned None
    order_ids = extraction.order_ids if extraction.order_ids else state.get("order_ids", [])
    refund_amount = (
        extraction.refund_amount
        if extraction.refund_amount is not None
        else state.get("refund_amount")
    )
    item_indices = (
        extraction.item_indices if extraction.item_indices else state.get("item_indices", [])
    )
    new_address = extraction.new_address or state.get("new_address")

    logger.info(
        "Structured extraction completed",
        trace_id=trace_id,
        intents=extracted_intents,
        order_ids=order_ids,
        refund_amount=refund_amount,
        conditions=extraction.conditions,
        actions=extraction.actions,
        latency_ms=latency,
    )

    return {
        "extracted_intents": extracted_intents,
        "order_ids": order_ids,
        "refund_amount": refund_amount,
        "item_indices": item_indices,
        "new_address": new_address,
        "conditions": extraction.conditions,
        "actions": extraction.actions,
        # Note: escalation_required from LLM is advisory only.
        # policy_validation_node makes the authoritative governance decision.
        "node_latencies": existing_latencies,
        "node_transitions": existing_transitions,
    }


async def _extract_with_llm(message: str, trace_id: str) -> Optional[IntentExtraction]:
    """
    Call Groq LLM with the extraction prompt and parse the JSON response.

    Returns None on any failure so the caller can gracefully fall back.
    """
    messages = [
        {"role": "system", "content": EXTRACTION_PROMPT},
        {"role": "user", "content": f"Customer message: {message}"},
    ]

    response = await chat(messages, tools=None)

    # Groq returns plain text JSON when no tools are passed
    raw_text = response.text or ""

    # Strip markdown code fences if present
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]) if len(lines) > 2 else text

    data = json.loads(text)
    return IntentExtraction(**data)
