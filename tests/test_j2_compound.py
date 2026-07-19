"""
J2 — Compound Request Journey Test

Validates the multi-step compound request flow:
- Cancel line item
- Refund (blocked by guardrail, escalated to CRM)
- Update shipping address

Expected trace: OMS cancel + CRM case (escalation) + OMS address update
The payments tool call should NOT appear in trace (blocked pre-execution).
"""

import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_j2_compound():
    """Test compound request: cancel + refund + address update."""
    response = client.post("/query", json={
        "message": "Cancel my order ORD-J2 item 1, refund me 85000, and update my address to New Address.",
        "session_id": "test-j2-compound",
    })

    assert response.status_code == 200
    data = response.json()

    assert "response" in data
    assert "trace" in data

    trace = data["trace"]

    # Verify trace metadata
    assert "trace_id" in trace
    assert "session_id" in trace
    assert "latency_ms" in trace
    assert trace["latency_ms"] > 0

    # Check tool calls
    tools_called = [tc["tool"] for tc in trace["tool_calls"]]
    ops_called = [tc["params"].get("operation") for tc in trace["tool_calls"]]

    # Must have OMS cancel and OMS address update
    assert "oms" in tools_called
    assert "cancel_line_item" in ops_called
    assert "update_shipping_address" in ops_called

    # Must have CRM case created (escalation for ₹85000 > ₹25000)
    assert "crm" in tools_called
    crm_calls = [
        tc for tc in trace["tool_calls"]
        if tc["tool"] == "crm" and tc["params"].get("operation") == "create_case"
    ]
    assert len(crm_calls) == 1, "Exactly one CRM case should be created"

    # CRM case must have trace_id linkage for audit
    assert crm_calls[0]["params"]["trace_id"] == trace["trace_id"]

    # Payments tool should NOT appear in trace (blocked by pre-execution guardrail)
    payments_calls = [tc for tc in trace["tool_calls"] if tc["tool"] == "payments"]
    assert len(payments_calls) == 0, (
        "Payments tool should be blocked pre-execution by guardrail"
    )


def test_j2_response_contains_escalation_info():
    """Verify the response text mentions the escalation."""
    response = client.post("/query", json={
        "message": "Cancel my order ORD-J2 item 1, refund me 85000, and update my address to New Address.",
        "session_id": "test-j2-escalation-info",
    })

    data = response.json()
    response_text = data["response"].lower()

    # Response should mention what was done and what was escalated
    assert "cancel" in response_text or "cancelled" in response_text
    assert "case" in response_text or "escalat" in response_text


def test_j2_tool_call_order():
    """Verify tool calls follow dependency order: cancel before refund attempt."""
    response = client.post("/query", json={
        "message": "Cancel my order ORD-J2 item 1, refund me 85000, and update my address to New Address.",
        "session_id": "test-j2-order",
    })

    data = response.json()
    trace = data["trace"]

    # Find the index of the cancel operation
    cancel_idx = None
    crm_idx = None
    for i, tc in enumerate(trace["tool_calls"]):
        if tc["params"].get("operation") == "cancel_line_item":
            cancel_idx = i
        if tc["tool"] == "crm":
            crm_idx = i

    # Cancel must happen before CRM escalation
    if cancel_idx is not None and crm_idx is not None:
        assert cancel_idx < crm_idx, (
            "Cancel should execute before CRM escalation case creation"
        )
