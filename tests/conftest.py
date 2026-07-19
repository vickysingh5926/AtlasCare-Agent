"""
Tests Configuration — Shared fixtures for AtlasCare tests.

Provides reusable fixtures for all journey tests, guardrail tests,
and negative tests.
"""

import pytest
from fastapi.testclient import TestClient
from main import app


@pytest.fixture
def api_client():
    """Yields a FastAPI TestClient."""
    with TestClient(app) as client:
        yield client


@pytest.fixture
def tracking_query():
    """J1 — Simple tracking query payload."""
    return {
        "message": "Where is my order ORD-J1?",
        "session_id": "test-session-j1",
    }


@pytest.fixture
def compound_query():
    """J2 — Compound multi-step query payload."""
    return {
        "message": "Cancel my order ORD-J2 item 1, refund me 85000, and update my address to New Address.",
        "session_id": "test-session-j2",
    }


@pytest.fixture
def escalation_query():
    """J3 — Escalation query payload."""
    return {
        "message": "Cancel order ORD-J3 and refund me 42000.",
        "session_id": "test-session-j3",
    }


@pytest.fixture
def policy_query():
    """J4 — Policy lookup query payload."""
    return {
        "message": "What is your return policy?",
        "session_id": "test-session-j4",
    }


def generate_safe_refund():
    """Returns a safe payload for testing refunds (under ₹25,000)."""
    return {
        "amount": 5000.0,
        "currency": "INR",
        "order_id": "ORD-TEST",
    }


def generate_unsafe_refund():
    """Returns an unsafe payload (triggers ₹25,000 threshold)."""
    return {
        "amount": 50000.0,
        "currency": "INR",
        "order_id": "ORD-TEST",
    }
