"""
Multi-Step Planner Module

For compound requests (J2), decomposes the user query into an ordered
list of execution steps. Each step maps to a tool call with parameters.

The planner ensures causal dependencies are respected:
- Cancel must happen before refund
- Address update is independent and can happen last
"""

from typing import Any, Dict, List
from agent.intent import Intent, extract_entities
from utils.logger import logger


def generate_plan(
    intent: Intent, query: str, customer_id: str
) -> List[Dict[str, Any]]:
    """
    Generate an ordered execution plan for the given intent.

    For COMPOUND requests, decomposes into sequential steps with
    dependency ordering. For simple intents, returns a single-step plan.

    Args:
        intent: Classified intent of the query.
        query: Raw user query string.
        customer_id: Customer identifier for CRM operations.

    Returns:
        Ordered list of plan steps, each with tool name and parameters.
    """
    entities = extract_entities(query)
    order_id = entities.get("order_id")

    logger.info(
        "Generating plan",
        intent=intent.value,
        entities=entities,
        customer_id=customer_id,
    )

    if intent == Intent.TRACKING:
        return _plan_tracking(order_id)
    elif intent == Intent.COMPOUND:
        return _plan_compound(entities, customer_id)
    elif intent == Intent.ESCALATION:
        return _plan_escalation(entities, customer_id)
    elif intent == Intent.POLICY:
        return _plan_policy(query)
    else:
        # GENERAL — let the LLM handle it via the orchestrator loop
        return []


def _plan_tracking(order_id: str | None) -> List[Dict[str, Any]]:
    """Single-step plan: fetch order status."""
    if not order_id:
        return []
    return [
        {
            "step": 1,
            "description": "Retrieve order status",
            "tool": "oms",
            "params": {"operation": "get_order_status", "order_id": order_id},
        }
    ]


def _plan_compound(
    entities: Dict[str, Any], customer_id: str
) -> List[Dict[str, Any]]:
    """
    Multi-step plan for compound requests.

    Ordering logic:
    1. Cancel item first (must happen before refund)
    2. Initiate refund (depends on cancellation)
    3. Update address (independent, can be last)
    """
    plan = []
    step = 1
    order_id = entities.get("order_id")
    query_lower = str(entities).lower()

    # Step 1: Cancel line item if requested
    if entities.get("item_index") and order_id:
        plan.append(
            {
                "step": step,
                "description": "Cancel line item",
                "tool": "oms",
                "params": {
                    "operation": "cancel_line_item",
                    "order_id": order_id,
                    "item_index": int(entities["item_index"]),
                },
            }
        )
        step += 1

    # Step 2: Initiate refund if amount specified
    if entities.get("amount") and order_id:
        plan.append(
            {
                "step": step,
                "description": "Process refund",
                "tool": "payments",
                "params": {
                    "operation": "initiate_refund",
                    "order_id": order_id,
                    "amount": int(entities["amount"]),
                },
            }
        )
        step += 1

    # Step 3: Update address if specified
    if entities.get("new_address") and order_id:
        plan.append(
            {
                "step": step,
                "description": "Update shipping address",
                "tool": "oms",
                "params": {
                    "operation": "update_shipping_address",
                    "order_id": order_id,
                    "new_address": entities["new_address"],
                },
            }
        )
        step += 1

    logger.info("Compound plan generated", steps=len(plan), plan=plan)
    return plan


def _plan_escalation(
    entities: Dict[str, Any], customer_id: str
) -> List[Dict[str, Any]]:
    """
    Plan for escalation-candidate queries.

    Follows the pattern: cancel first, then attempt refund
    (guardrail will block if over threshold), then CRM case.
    """
    plan = []
    step = 1
    order_id = entities.get("order_id")

    # Step 1: Cancel if order referenced
    if order_id:
        plan.append(
            {
                "step": step,
                "description": "Cancel order item",
                "tool": "oms",
                "params": {
                    "operation": "cancel_line_item",
                    "order_id": order_id,
                    "item_index": 1,
                },
            }
        )
        step += 1

    # Step 2: Attempt refund (guardrail will intercept if > Rs.25,000)
    if entities.get("amount") and order_id:
        plan.append(
            {
                "step": step,
                "description": "Attempt refund (subject to guardrail)",
                "tool": "payments",
                "params": {
                    "operation": "initiate_refund",
                    "order_id": order_id,
                    "amount": int(entities["amount"]),
                },
            }
        )
        step += 1

    return plan


def _plan_policy(query: str) -> List[Dict[str, Any]]:
    """Single-step plan: search knowledge base."""
    return [
        {
            "step": 1,
            "description": "Search knowledge base for policy",
            "tool": "kb",
            "params": {"operation": "search_policy", "query": query},
        }
    ]
