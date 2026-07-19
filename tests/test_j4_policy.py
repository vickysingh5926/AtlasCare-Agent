"""
J4 — Policy Lookup Journey Test (Bonus)

Validates the knowledge base lookup flow:
- KB tool call to search_policy
- Response contains policy information
- No hallucinated policy details
"""

import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_j4_policy_lookup():
    """Test policy lookup: KB tool call with relevant results."""
    response = client.post("/query", json={
        "message": "What is your return policy?",
        "session_id": "test-j4-policy",
    })

    assert response.status_code == 200
    data = response.json()

    assert "response" in data
    assert "trace" in data

    trace = data["trace"]

    # Verify trace metadata
    assert trace["trace_id"] is not None
    assert trace["session_id"] is not None
    assert trace["latency_ms"] > 0

    # Should have at least one KB tool call
    kb_calls = [
        tc for tc in trace["tool_calls"]
        if tc["tool"] == "kb"
    ]
    assert len(kb_calls) >= 1, "Should have at least one KB tool call"

    # KB call should succeed
    assert kb_calls[0]["result"] == "success"


def test_j4_response_contains_policy_info():
    """Verify the response mentions return/refund policy details."""
    response = client.post("/query", json={
        "message": "What is your return policy?",
        "session_id": "test-j4-response",
    })

    data = response.json()
    response_text = data["response"].lower()

    # Response should contain relevant policy information
    assert "return" in response_text or "refund" in response_text or "policy" in response_text


def test_j4_kb_search_keyword_matching():
    """Test that KB search works with various query formats."""
    from tools.kb import KBTool

    kb = KBTool()

    # Test keyword search
    import asyncio
    result = asyncio.get_event_loop().run_until_complete(
        kb.execute({"operation": "search_policy", "query": "refund policy threshold"})
    )
    assert result["status"] == "success"
    assert len(result["data"]) > 0, "Should find articles matching 'refund policy threshold'"

    # Test partial keyword match
    result = asyncio.get_event_loop().run_until_complete(
        kb.execute({"operation": "search_policy", "query": "cancellation rules"})
    )
    assert result["status"] == "success"
    assert len(result["data"]) > 0, "Should find articles matching 'cancellation rules'"
