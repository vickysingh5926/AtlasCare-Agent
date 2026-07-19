"""
Customer Relationship Management (CRM) Tool

Provides customer operations:
- get_customer_profile: Retrieve customer details, tier, addresses
- create_case: Create an escalation/support case with trace linkage

Data source: data/customers.json (mock)
"""

import json
import os
import uuid
from typing import Any, Dict, List

from .base import BaseTool

# In-memory store for created cases (persists across requests within a session)
_created_cases: List[Dict[str, Any]] = []


def _load_customers() -> dict:
    """Load customer data from JSON file."""
    path = os.path.join(os.path.dirname(__file__), "..", "data", "customers.json")
    with open(path) as f:
        return json.load(f)


class CRMTool(BaseTool):
    """Customer Relationship Management — profiles and support cases."""

    name = "crm"
    description = (
        "Customer Relationship Management system. Use this tool to: "
        "(1) get_customer_profile — retrieve customer details including name, "
        "email, phone, loyalty tier, and addresses; "
        "(2) create_case — create a support/escalation case for human agents. "
        "Use create_case whenever: (a) a refund exceeds Rs.25,000, "
        "(b) a tool call fails and requires human intervention, or "
        "(c) the customer explicitly asks for human support. "
        "IMPORTANT: When creating a case, ALWAYS include the trace_id "
        "for audit linkage, a descriptive summary, and the appropriate "
        "priority level (low/medium/high/critical)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["get_customer_profile", "create_case"],
                "description": "The CRM operation to perform.",
            },
            "customer_id": {
                "type": "string",
                "description": "Customer ID like CUST-XXX.",
            },
            "summary": {
                "type": "string",
                "description": "Case summary describing the issue. Required for create_case.",
            },
            "priority": {
                "type": "string",
                "enum": ["low", "medium", "high", "critical"],
                "description": "Case priority level. Required for create_case.",
            },
            "trace_id": {
                "type": "string",
                "description": "Trace ID for audit linkage. Required for create_case.",
            },
        },
        "required": ["operation", "customer_id"],
    }

    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a CRM operation against mock customer data."""
        data = _load_customers()
        customers_list = data.get("customers", [])
        customers_dict = {c["customer_id"]: c for c in customers_list}

        op = params.get("operation")
        cust_id = params.get("customer_id")

        if op == "get_customer_profile":
            if cust_id not in customers_dict:
                return {"status": "error", "message": f"Customer {cust_id} not found"}
            return {
                "status": "success",
                "message": f"Profile retrieved for {cust_id}",
                "data": customers_dict[cust_id],
            }

        elif op == "create_case":
            # Generate unique case ID
            case_id = f"CASE-{uuid.uuid4().hex[:8].upper()}"
            case_record = {
                "case_id": case_id,
                "customer_id": cust_id,
                "summary": params.get("summary", "No summary provided"),
                "priority": params.get("priority", "medium"),
                "trace_id": params.get("trace_id", ""),
                "status": "open",
            }
            _created_cases.append(case_record)

            return {
                "status": "success",
                "message": f"Support case {case_id} created for customer {cust_id}",
                "case_id": case_id,
                "trace_id": params.get("trace_id", ""),
            }

        return {"status": "error", "message": f"Unknown CRM operation: {op}"}
