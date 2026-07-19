"""
Payments Tool

Provides payment operations:
- initiate_refund: Process a refund for an order

SAFETY: This tool contains a SECONDARY guardrail check (defense-in-depth).
The PRIMARY check is in the orchestrator's pre-execution guardrail.
Even if the orchestrator check is somehow bypassed, this tool-level
check will still block refunds exceeding ₹25,000.

Data source: data/payments_config.json (for supported methods only)
"""

from typing import Any, Dict

from .base import BaseTool
from guardrails.refund_limit import check_refund_threshold


class PaymentsTool(BaseTool):
    """Payment Gateway — refund processing with built-in safety guard."""

    name = "payments"
    description = (
        "Payment Gateway for processing refunds. Use this tool to: "
        "(1) initiate_refund — process a refund for a given order. "
        "Requires order_id and amount in INR. The payment_method is optional "
        "(defaults to original payment method)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["initiate_refund"],
                "description": "The payment operation to perform.",
            },
            "order_id": {
                "type": "string",
                "description": "Order ID for the refund.",
            },
            "amount": {
                "type": "number",
                "description": "Refund amount in INR.",
            },
            "payment_method": {
                "type": "string",
                "description": "Payment method for refund (e.g. HDFC_CREDIT). Optional.",
            },
        },
        "required": ["operation", "order_id", "amount"],
    }

    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a payment operation.

        Contains a SECONDARY hard-coded guardrail as defense-in-depth.
        The primary guardrail is in the orchestrator's pre-execution check.
        """
        op = params.get("operation")

        if op == "initiate_refund":
            # DEFENSE-IN-DEPTH: Secondary hard-coded guardrail check
            guard_result = check_refund_threshold(self.name, params)
            if guard_result.get("blocked"):
                return {
                    "status": "error",
                    "message": guard_result["reason"],
                    "action": "escalate",
                }

            amount = params.get("amount", 0)
            method = params.get("payment_method", "original")
            order_id = params.get("order_id")
            return {
                "status": "success",
                "message": (
                    f"Refund of ₹{amount:,} initiated for order {order_id} "
                    f"via {method}"
                ),
                "refund_amount": amount,
                "payment_method": method,
            }

        return {"status": "error", "message": f"Unknown payments operation: {op}"}
