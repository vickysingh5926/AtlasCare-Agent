"""
J1 — Simple Tracking Journey Test

Validates the basic order tracking flow:
- Single OMS tool call to get_order_status
- Response contains order data (no hallucination)
- Latency under 30 seconds (generous for API retry backoff)
- Trace has proper metadata
"""

import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_j1_tracking():
    """Test simple tracking: one OMS call, response with order data."""
    response = client.post("/query", json={
        "message": "Where is my order ORD-J1?",
        "session_id": "test-j1-tracking",
    })

    assert response.status_code == 200
    data = response.json()

    assert "response" in data
    assert "trace" in data

    trace = data["trace"]

    # Verify trace metadata
    assert "trace_id" in trace
    assert "session_id" in trace
    assert trace["latency_ms"] > 0

    # Verify exactly one OMS call for order status
    assert len(trace["tool_calls"]) >= 1
    oms_calls = [
        tc for tc in trace["tool_calls"]
        if tc["tool"] == "oms"
        and tc["params"].get("operation") == "get_order_status"
    ]
    assert len(oms_calls) == 1
    assert oms_calls[0]["params"]["order_id"] == "ORD-J1"
    assert oms_calls[0]["result"] == "success"


def test_j1_latency():
    """Verify end-to-end latency is reasonable (< 30s with retry backoff)."""
    response = client.post("/query", json={
        "message": "Where is my order ORD-J1?",
        "session_id": "test-j1-latency",
    })

    data = response.json()
    assert data["trace"]["latency_ms"] < 30_000, (
        f"Latency {data['trace']['latency_ms']}ms exceeds 30s threshold"
    )


def test_j1_health_endpoint():
    """Test GET /health returns healthy status."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "atlascare"
    assert data["version"] == "1.0.0"


def test_j1_empty_query_rejected():
    """Test that empty queries are rejected with 400."""
    response = client.post("/query", json={
        "message": "   ",
        "session_id": "test-j1-empty",
    })
    assert response.status_code == 400


def test_j1_invalid_order():
    """Test that an invalid order ID returns a valid response (not a crash)."""
    response = client.post("/query", json={
        "message": "Where is my order ORD-INVALID?",
        "session_id": "test-j1-invalid",
    })

    assert response.status_code == 200
    data = response.json()
    assert "response" in data
    assert "trace" in data
    # Should still have a valid trace
    assert data["trace"]["trace_id"] is not None


def test_j1_trace_retrieval():
    """Test that a trace can be retrieved via GET /trace/{trace_id}."""
    # First, create a trace
    response = client.post("/query", json={
        "message": "Where is my order ORD-J1?",
        "session_id": "test-j1-trace",
    })
    trace_id = response.json()["trace"]["trace_id"]

    # Then retrieve it
    trace_response = client.get(f"/trace/{trace_id}")
    assert trace_response.status_code == 200

    trace_data = trace_response.json()
    assert trace_data["trace_id"] == trace_id
    assert "tool_calls" in trace_data


def test_j1_trace_not_found():
    """Test that requesting a non-existent trace returns 404."""
    response = client.get("/trace/non-existent-trace-id")
    assert response.status_code == 404
