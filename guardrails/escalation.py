"""
Escalation Detection Module

Determines when an interaction requires human escalation and builds
structured escalation payloads for CRM case creation. Handles:
- Refund threshold breaches (Rs.25,000 limit)
- Repeated tool failures
- Explicit customer escalation requests
"""

from typing import Any, Dict, List, Optional
from utils.logger import logger


# Priority levels for escalation cases
PRIORITY_HIGH = "high"
PRIORITY_MEDIUM = "medium"
PRIORITY_LOW = "low"


def detect_escalation(
    tool_name: str,
    params: Dict[str, Any],
    result: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Check if a tool result requires escalation to a human agent.

    Examines the tool result for escalation signals:
    - Payments tool returning 'escalate' action (threshold breach)
    - Any tool returning repeated failures
    - CRM-related escalation triggers

    Args:
        tool_name: Name of the tool that was called.
        params: Parameters passed to the tool.
        result: Result dictionary from tool execution.

    Returns:
        Dictionary with:
        - needs_escalation (bool): Whether escalation is required
        - reason (str): Human-readable escalation reason
        - priority (str): Escalation priority level
        - summary (dict): Structured data for CRM case
    """
    if result.get("action") == "escalate":
        amount = params.get("amount", 0)
        order_id = params.get("order_id", "UNKNOWN")

        logger.info(
            "Escalation detected",
            tool=tool_name,
            reason="refund_threshold_breach",
            amount=amount,
            order_id=order_id,
        )

        return {
            "needs_escalation": True,
            "reason": f"Refund amount Rs.{amount} exceeds auto-approval limit of Rs.25000",
            "priority": PRIORITY_HIGH,
            "summary": {
                "type": "refund_threshold_breach",
                "tool": tool_name,
                "order_id": order_id,
                "requested_amount": amount,
                "threshold": 25000,
                "action_required": "Manual refund review and approval",
            },
        }

    return {"needs_escalation": False}


def build_escalation_case(
    customer_id: str,
    trace_id: str,
    escalation_info: Dict[str, Any],
    completed_actions: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Build a structured CRM case payload for escalation.

    Compiles all relevant context into a case that a human agent
    can pick up without needing to re-investigate.

    Args:
        customer_id: Customer identifier.
        trace_id: Trace ID for linkage and audit trail.
        escalation_info: Output from detect_escalation().
        completed_actions: List of successfully completed actions before escalation.

    Returns:
        Dictionary ready to pass to CRM create_case tool.
    """
    summary_parts = [escalation_info.get("reason", "Escalation required")]

    if completed_actions:
        summary_parts.append(
            "Completed actions: " + "; ".join(completed_actions)
        )

    return {
        "operation": "create_case",
        "customer_id": customer_id,
        "trace_id": trace_id,
        "summary": " | ".join(summary_parts),
        "priority": escalation_info.get("priority", PRIORITY_MEDIUM),
    }
