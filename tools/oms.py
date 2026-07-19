"""
Order Management System (OMS) Tool

Provides order lifecycle operations:
- get_order_status: Retrieve full order details and tracking info
- cancel_line_item: Cancel a specific item from an order
- update_shipping_address: Change the delivery address for an order

Data source: data/orders.json (mock)
"""

import json
import os
from functools import lru_cache
from typing import Any, Dict

from .base import BaseTool


@lru_cache(maxsize=1)
def _load_orders() -> dict:
    """Load and cache order data from JSON file."""
    path = os.path.join(os.path.dirname(__file__), "..", "data", "orders.json")
    with open(path) as f:
        return json.load(f)


class OMSTool(BaseTool):
    """Order Management System — order status, cancellation, address updates."""

    name = "oms"
    description = (
        "Order Management System for order lifecycle operations. Use this tool to: "
        "(1) get_order_status — retrieve current status, tracking number, "
        "estimated delivery date, items, and shipping address for an order; "
        "(2) cancel_line_item — cancel a specific item from an order by index "
        "(1-based). IMPORTANT: You MUST cancel an item BEFORE attempting any "
        "refund for that order; "
        "(3) update_shipping_address — change the delivery address on an order. "
        "This operation is independent and can be done at any point. "
        "All operations require an order_id like ORD-XXXXX."
    )
    parameters = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["get_order_status", "cancel_line_item", "update_shipping_address"],
                "description": "The operation to perform on the order.",
            },
            "order_id": {
                "type": "string",
                "description": "Order ID in the format ORD-XXXXX.",
            },
            "item_index": {
                "type": "integer",
                "description": "Index of the line item to cancel (1-based). Required for cancel_line_item.",
            },
            "new_address": {
                "type": "string",
                "description": "New shipping address. Required for update_shipping_address.",
            },
        },
        "required": ["operation", "order_id"],
    }

    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute an OMS operation against mock order data."""
        data = _load_orders()
        orders_list = data.get("orders", [])
        orders_dict = {o["order_id"]: o for o in orders_list}

        op = params.get("operation")
        order_id = params.get("order_id")

        if order_id not in orders_dict:
            return {"status": "error", "message": f"Order {order_id} not found"}

        order = orders_dict[order_id]

        if op == "get_order_status":
            return {
                "status": "success",
                "message": f"Order {order_id} is currently {order['status']}",
                "data": order,
            }

        elif op == "cancel_line_item":
            item_index = params.get("item_index", 1)
            items = order.get("items", [])
            if item_index < 1 or item_index > len(items):
                return {
                    "status": "error",
                    "message": f"Item index {item_index} out of range (1-{len(items)})",
                }
            item_name = items[item_index - 1].get("name", f"item {item_index}")
            return {
                "status": "success",
                "message": f"Item {item_index} ({item_name}) cancelled from order {order_id}",
            }

        elif op == "update_shipping_address":
            new_address = params.get("new_address", "")
            if not new_address:
                return {"status": "error", "message": "No new address provided"}
            return {
                "status": "success",
                "message": f"Shipping address for {order_id} updated to: {new_address}",
            }

        return {"status": "error", "message": f"Unknown OMS operation: {op}"}
