"""
J3 — Escalation Journey Test

Validates the escalation flow for high-value refunds:
- Cancel order item (succeeds)
- Refund ₹42,000 blocked by pre-execution guardrail (₹25,000 limit)
- CRM case auto-created with trace_id linkage
- NO payments tool call in trace (proves guardrail works at code level)
"""

import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_j3_escalation():
    """Test escalation: cancel + refund blocked + CRM case created."""
    response = client.post("/query", json={
        "message": "Cancel order ORD-J3 and refund me 42000.",
        "session_id": "test-j3-escalation",
    })

    assert response.status_code == 200
    data = response.json()

    trace = data["trace"]

    # 1. Verify NO payments tool call exists in trace
    #    This is the audit proof that the guardrail blocked it pre-execution
    payments_calls = [tc for tc in trace["tool_calls"] if tc["tool"] == "payments"]
    assert len(payments_calls) == 0, \
        "Payments tool must NOT appear in trace — guardrail should block pre-execution"

    # 2. Verify OMS cancel was executed
    oms_calls = [
        tc for tc in trace["tool_calls"]
        if tc["tool"] == "oms"
        and tc["params"].get("operation") == "cancel_line_item"
    ]
    assert len(oms_calls) >= 1, "OMS cancel should be executed"

    # 3. Verify CRM case was created with trace_id linkage
    crm_calls = [
        tc for tc in trace["tool_calls"]
        if tc["tool"] == "crm"
        and tc["params"].get("operation") == "create_case"
    ]
    assert len(crm_calls) == 1, "Exactly one CRM case should be created"
    assert crm_calls[0]["params"]["trace_id"] == trace["trace_id"], \
        "CRM case must have trace_id for audit linkage"

    # 4. Verify trace metadata
    assert trace["latency_ms"] > 0
    assert trace["trace_id"] is not None
    assert trace["session_id"] is not None


def test_j3_response_mentions_escalation():
    """Verify response text communicates the escalation clearly."""
    response = client.post("/query", json={
        "message": "Cancel order ORD-J3 and refund me 42000.",
        "session_id": "test-j3-response",
    })

    data = response.json()
    response_text = data["response"].lower()

    # Must mention escalation/case creation
    assert "case" in response_text or "escalat" in response_text
    # Must mention the refund issue
    assert "refund" in response_text


def test_j3_crm_case_has_summary():
    """Verify the CRM case contains a meaningful summary."""
    response = client.post("/query", json={
        "message": "Cancel order ORD-J3 and refund me 42000.",
        "session_id": "test-j3-summary",
    })

    data = response.json()
    trace = data["trace"]

    crm_calls = [
        tc for tc in trace["tool_calls"]
        if tc["tool"] == "crm"
        and tc["params"].get("operation") == "create_case"
    ]
    assert len(crm_calls) == 1

    # CRM case should have a summary
    summary = crm_calls[0]["params"].get("summary", "")
    assert len(summary) > 0, "CRM case summary should not be empty"


def test_j3_guardrail_threshold_edge_case():
    """Test that exactly ₹25,000 passes (not greater than)."""
    from guardrails.refund_limit import check_refund_threshold

    # Exactly 25000 should NOT be blocked (limit is "above 25000")
    result = check_refund_threshold(
        "payments", {"operation": "initiate_refund", "amount": 25000}
    )
    assert not result.get("blocked"), "₹25,000 should not be blocked (boundary case)"

    # 25001 should be blocked
    result = check_refund_threshold(
        "payments", {"operation": "initiate_refund", "amount": 25001}
    )
    assert result.get("blocked"), "₹25,001 should be blocked"

    # 42000 should be blocked
    result = check_refund_threshold(
        "payments", {"operation": "initiate_refund", "amount": 42000}
    )
    assert result.get("blocked"), "₹42,000 should be blocked"


def test_j3_guardrail_non_payment_tool_passes():
    """Verify the guardrail only blocks payments tool, not others."""
    from guardrails.refund_limit import check_refund_threshold

    # OMS tool should never be blocked by refund guardrail
    result = check_refund_threshold(
        "oms", {"operation": "get_order_status", "amount": 50000}
    )
    assert not result.get("blocked"), "Non-payment tools should never be blocked"
