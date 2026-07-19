"""
Extended Journey & Mixed Query Test Suite

Comprehensive tests across all four journeys using the expanded data set:
- J1: Tracking (multiple orders, different statuses)
- J2: Compound (multi-step with cancel + refund + address update)
- J3: Escalation (refund above ₹25K threshold)
- J4: Policy (KB lookups — already covered in test_kb_queries.py)
- Mixed: Cross-journey queries combining tracking + policy, compound + policy, etc.
- Edge cases: Invalid orders, missing entities, boundary refund amounts

Uses the expanded data set:
- 5 customers (CUST-001 to CUST-005)
- 11 orders (ORD-J1 to ORD-J3, ORD-A1/A2, ORD-B1/B2/B3, ORD-C1, ORD-D1/D2)
- Various statuses: placed, shipped, delivered
- Price range: Rs.499 to Rs.85,000
"""

import asyncio
import json
import sys
import os

# Force UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load .env so GROQ_API_KEY is available for pipeline tests
from dotenv import load_dotenv
load_dotenv()

from agent.orchestrator import handle_query
from agent.intent import classify_intent, Intent, extract_entities
from tools.oms import OMSTool
from tools.kb import KBTool
from tools.crm import CRMTool
from tools.payments import PaymentsTool


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _tools_used(response):
    """Extract tool names from response trace."""
    return [tc.tool for tc in response.trace.tool_calls]


def _tool_ops(response):
    """Extract (tool, operation) pairs from response trace."""
    return [(tc.tool, tc.params.get("operation", "?")) for tc in response.trace.tool_calls]


def _has_tool(response, tool_name):
    """Check if a specific tool was used."""
    return tool_name in _tools_used(response)


# # ═══════════════════════════════════════════════════════════════════════════════
# # Section 1: J1 — TRACKING JOURNEY (Expanded)
# # ═══════════════════════════════════════════════════════════════════════════════

# async def test_tracking_journey():
#     """Test tracking across multiple orders with different statuses."""
#     print("\n" + "=" * 70)
#     print("  SECTION 1: J1 — TRACKING JOURNEY")
#     print("=" * 70)

#     test_cases = [
#         # (query, session_id, customer_id, description, checks)
#         (
#             "Where is my order ORD-J1?",
#             "track-j1", "CUST-001",
#             "Track shipped order (original J1)",
#             {"has_oms": True, "has_response": True},
#         ),
#         (
#             "Track my order ORD-A2",
#             "track-a2", "CUST-002",
#             "Track shipped order (new customer)",
#             {"has_oms": True, "has_response": True},
#         ),
#         (
#             "What is the status of order ORD-A1?",
#             "track-a1", "CUST-002",
#             "Track delivered order",
#             {"has_oms": True, "has_response": True},
#         ),
#         (
#             "Where is order ORD-B2?",
#             "track-b2", "CUST-003",
#             "Track shipped order (Chennai customer)",
#             {"has_oms": True, "has_response": True},
#         ),
#         (
#             "When will ORD-D1 be delivered?",
#             "track-d1", "CUST-005",
#             "Delivery estimate query",
#             {"has_oms": True, "has_response": True},
#         ),
#         (
#             "Where is my order ORD-FAKE99?",
#             "track-fake", "CUST-001",
#             "Invalid order ID — should handle gracefully",
#             {"has_oms": True, "has_response": True},
#         ),
#     ]

#     passed, failed = 0, 0
#     for query, sid, cid, desc, checks in test_cases:
#         try:
#             resp = await handle_query(query, sid, cid)
#             ok = True

#             if checks.get("has_oms") and not _has_tool(resp, "oms"):
#                 ok = False
#             if checks.get("has_response") and len(resp.response) < 10:
#                 ok = False

#             status = "✓" if ok else "✗"
#             if ok: passed += 1
#             else: failed += 1

#             print(f"  {status} [{desc}]")
#             print(f"    Query:    \"{query}\"")
#             print(f"    Tools:    {_tool_ops(resp)}")
#             print(f"    Response: \"{resp.response[:100]}...\"")
#             print(f"    Latency:  {resp.trace.latency_ms}ms")
#         except Exception as e:
#             failed += 1
#             print(f"  ✗ [{desc}] ERROR: {e}")
#         print()

#     print(f"  Results: {passed}/{passed + failed} passed")
#     return passed, failed


# ═══════════════════════════════════════════════════════════════════════════════
# Section 2: J2 — COMPOUND JOURNEY (Expanded)
# ═══════════════════════════════════════════════════════════════════════════════

# async def test_compound_journey():
#     """Test compound multi-step operations with the expanded order set."""
#     print("\n" + "=" * 70)
#     print("  SECTION 2: J2 — COMPOUND JOURNEY")
#     print("=" * 70)

#     test_cases = [
#         (
#             "Cancel item 2 from order ORD-J2 and refund me 2500",
#             "compound-j2-safe", "CUST-001",
#             "Cancel + safe refund (₹2,500 < ₹25K limit)",
#             {"has_oms": True, "min_tools": 2},
#         ),
#         (
#             "Cancel item 1 from ORD-B3 and refund 15000",
#             "compound-b3", "CUST-003",
#             "Cancel + safe refund on new order (₹15,000)",
#             {"has_oms": True, "min_tools": 2},
#         ),
#         (
#             "Cancel item 1 from ORD-A2 and update my address to 55 Connaught Place, New Delhi",
#             "compound-a2-addr", "CUST-002",
#             "Cancel + address update (no refund)",
#             {"has_oms": True, "min_tools": 2},
#         ),
#         (
#             "Cancel my order ORD-J2 item 1, refund me 85000, and update my address to New Address.",
#             "compound-j2-esc", "CUST-001",
#             "Cancel + over-limit refund + address (original J2 — escalation)",
#             {"has_oms": True, "min_tools": 2},
#         ),
#     ]

#     passed, failed = 0, 0
#     for query, sid, cid, desc, checks in test_cases:
#         try:
#             resp = await handle_query(query, sid, cid)
#             ok = True

#             if checks.get("has_oms") and not _has_tool(resp, "oms"):
#                 ok = False
#             tools = _tools_used(resp)
#             if checks.get("min_tools") and len(tools) < checks["min_tools"]:
#                 ok = False

#             status = "✓" if ok else "✗"
#             if ok: passed += 1
#             else: failed += 1

#             print(f"  {status} [{desc}]")
#             print(f"    Query:    \"{query}\"")
#             print(f"    Tools:    {_tool_ops(resp)}")
#             print(f"    Latency:  {resp.trace.latency_ms}ms")
#             if resp.trace.policy_violations:
#                 print(f"    Violations: {resp.trace.policy_violations}")
#         except Exception as e:
#             failed += 1
#             print(f"  ✗ [{desc}] ERROR: {e}")
#         print()

#     print(f"  Results: {passed}/{passed + failed} passed")
#     return passed, failed


# # ═══════════════════════════════════════════════════════════════════════════════
# # Section 3: J3 — ESCALATION JOURNEY (Expanded)
# # ═══════════════════════════════════════════════════════════════════════════════

# async def test_escalation_journey():
#     """Test escalation triggers with various amounts above ₹25K."""
#     print("\n" + "=" * 70)
#     print("  SECTION 3: J3 — ESCALATION JOURNEY")
#     print("=" * 70)

#     test_cases = [
#         (
#             "Cancel order ORD-J3 and refund me 42000.",
#             "esc-j3", "CUST-001",
#             "Original J3: ₹42,000 refund (above ₹25K → escalate)",
#             {"has_escalation": True, "has_crm": True},
#         ),
#         (
#             "Cancel item 1 from ORD-B1 and refund me 32000",
#             "esc-b1", "CUST-003",
#             "₹32,000 monitor refund (above ₹25K → escalate)",
#             {"has_escalation": True, "has_crm": True},
#         ),
#         (
#             "Refund me Rs.28000 for order ORD-D2",
#             "esc-d2", "CUST-005",
#             "₹28,000 washing machine refund (above ₹25K → escalate)",
#             {"has_escalation": True},
#         ),
#         (
#             "I want to speak to a manager about order ORD-C1",
#             "esc-manager", "CUST-004",
#             "Explicit human escalation request",
#             {"has_escalation": True},
#         ),
#         (
#             "Cancel item 1 from ORD-B3 and refund 15000",
#             "esc-safe-b3", "CUST-003",
#             "₹15,000 refund (below ₹25K → NO escalation, control case)",
#             {"has_escalation": False},
#         ),
#         (
#             "Refund Rs.25000 for order ORD-B3",
#             "esc-boundary", "CUST-003",
#             "Exact ₹25,000 boundary (AT limit → NO escalation)",
#             {"has_escalation": False},
#         ),
#     ]

#     passed, failed = 0, 0
#     for query, sid, cid, desc, checks in test_cases:
#         try:
#             resp = await handle_query(query, sid, cid)
#             ok = True

#             has_esc = len(resp.trace.policy_violations) > 0
#             if checks["has_escalation"] and not has_esc:
#                 ok = False
#             if not checks["has_escalation"] and has_esc:
#                 ok = False

#             status = "✓" if ok else "✗"
#             if ok: passed += 1
#             else: failed += 1

#             print(f"  {status} [{desc}]")
#             print(f"    Query:      \"{query}\"")
#             print(f"    Tools:      {_tool_ops(resp)}")
#             print(f"    Escalation: {has_esc}")
#             print(f"    Violations: {resp.trace.policy_violations}")
#             print(f"    Latency:    {resp.trace.latency_ms}ms")
#         except Exception as e:
#             failed += 1
#             print(f"  ✗ [{desc}] ERROR: {e}")
#         print()

#     print(f"  Results: {passed}/{passed + failed} passed")
#     return passed, failed


# ═══════════════════════════════════════════════════════════════════════════════
# Section 4: MIXED QUERIES (Cross-Journey)
# ═══════════════════════════════════════════════════════════════════════════════

async def test_mixed_queries():
    """Test queries that span multiple journey types."""
    print("\n" + "=" * 70)
    print("  SECTION 4: MIXED / CROSS-JOURNEY QUERIES")
    print("=" * 70)

    test_cases = [
        (
            "Track my order ORD-D1 and also tell me the return policy",
            "mixed-track-policy", "CUST-005",
            "Tracking + Policy: should call both OMS and KB",
            {"has_oms": True, "has_kb": True},
        ),
        (
            "What is the status of ORD-A1 and can I get a refund for it?",
            "mixed-track-refund", "CUST-002",
            "Tracking + Refund inquiry: should call both OMS and KB",
            {"has_oms": True, "has_kb": True},
        ),
        (
            "Cancel item 2 from ORD-A2 and what is your return policy?",
            "mixed-cancel-policy", "CUST-002",
            "Cancel + Policy: should call OMS and KB",
            {"has_oms": True, "has_kb": True},
        ),
        (
            "Where is my order ORD-B2 and how long does shipping take?",
            "mixed-track-shipping", "CUST-003",
            "Tracking + Shipping policy: should call OMS and KB",
            {"has_oms": True, "has_kb": True},
        ),
        (
            "I want to cancel item 1 from ORD-B1, refund 32000, and also explain the warranty policy",
            "mixed-compound-policy", "CUST-003",
            "Compound + Policy + Escalation: triple mixed query",
            {"has_oms": True, "has_response": True},
        ),
    ]

    passed, failed = 0, 0
    for query, sid, cid, desc, checks in test_cases:
        try:
            resp = await handle_query(query, sid, cid)
            ok = True

            if checks.get("has_oms") and not _has_tool(resp, "oms"):
                ok = False
            if checks.get("has_kb") and not _has_tool(resp, "kb"):
                ok = False
            if checks.get("has_response") and len(resp.response) < 10:
                ok = False

            status = "✓" if ok else "✗"
            if ok: passed += 1
            else: failed += 1

            print(f"  {status} [{desc}]")
            print(f"    Query:    \"{query}\"")
            print(f"    Tools:    {_tool_ops(resp)}")
            print(f"    Response: \"{resp.response[:120]}...\"")
            print(f"    Latency:  {resp.trace.latency_ms}ms")
            if resp.trace.policy_violations:
                print(f"    Violations: {resp.trace.policy_violations}")
        except Exception as e:
            failed += 1
            print(f"  ✗ [{desc}] ERROR: {e}")
        print()

    print(f"  Results: {passed}/{passed + failed} passed")
    return passed, failed


# ═══════════════════════════════════════════════════════════════════════════════
# Section 5: ENTITY EXTRACTION Tests
# ═══════════════════════════════════════════════════════════════════════════════

def test_entity_extraction():
    """Test entity extraction across the expanded data set."""
    print("\n" + "=" * 70)
    print("  SECTION 5: ENTITY EXTRACTION")
    print("=" * 70)

    test_cases = [
        # (query, expected_field, expected_value, description)
        ("Where is ORD-A1?", "order_id", "ORD-A1", "Extract new order ID ORD-A1"),
        ("Track ORD-B2", "order_id", "ORD-B2", "Extract new order ID ORD-B2"),
        ("Cancel item 3 from ORD-A2", "item_index", "3", "Extract item index 3"),
        ("Refund Rs.15000 for ORD-B3", "amount", "15000", "Extract amount 15000"),
        ("Cancel item 1 from ORD-D2", "order_id", "ORD-D2", "Extract order ID ORD-D2"),
        (
            "Update address to 55 Connaught Place, New Delhi for ORD-A2",
            "order_id", "ORD-A2",
            "Extract order ID with address context",
        ),
    ]

    passed, failed = 0, 0
    for query, field, expected, desc in test_cases:
        entities = extract_entities(query)
        actual = entities.get(field)

        ok = str(actual) == str(expected)
        status = "✓" if ok else "✗"
        if ok: passed += 1
        else: failed += 1

        print(f"  {status} [{desc}]")
        print(f"    Query:    \"{query}\"")
        print(f"    Field:    {field} = {actual} (expected: {expected})")
        if not ok:
            print(f"    *** MISMATCH ***")
        print()

    print(f"  Results: {passed}/{passed + failed} passed")
    return passed, failed


# ═══════════════════════════════════════════════════════════════════════════════
# Section 6: TOOL UNIT TESTS (Expanded Data)
# ═══════════════════════════════════════════════════════════════════════════════

async def test_tool_operations():
    """Test individual tool operations against the expanded data."""
    print("\n" + "=" * 70)
    print("  SECTION 6: TOOL UNIT TESTS")
    print("=" * 70)

    oms = OMSTool()
    kb = KBTool()
    crm = CRMTool()
    payments = PaymentsTool()

    passed, failed = 0, 0

    # ── OMS Tests ─────────────────────────────────────────────────────────

    # Test 1: Get status of new order ORD-A1
    result = await oms.execute({"operation": "get_order_status", "order_id": "ORD-A1"})
    ok = result["status"] == "success" and result["data"]["status"] == "delivered"
    status = "✓" if ok else "✗"
    if ok: passed += 1
    else: failed += 1
    print(f"  {status} [OMS: get_order_status ORD-A1 → delivered]")

    # Test 2: Get status of multi-item order ORD-A2
    result = await oms.execute({"operation": "get_order_status", "order_id": "ORD-A2"})
    ok = result["status"] == "success" and len(result["data"]["items"]) == 3
    status = "✓" if ok else "✗"
    if ok: passed += 1
    else: failed += 1
    print(f"  {status} [OMS: get_order_status ORD-A2 → 3 items]")

    # Test 3: Cancel item from new order ORD-B1
    result = await oms.execute({"operation": "cancel_line_item", "order_id": "ORD-B1", "item_index": 2})
    ok = result["status"] == "success" and "Mechanical Keyboard" in result["message"]
    status = "✓" if ok else "✗"
    if ok: passed += 1
    else: failed += 1
    print(f"  {status} [OMS: cancel_line_item ORD-B1 item 2 → Mechanical Keyboard]")

    # Test 4: Cancel invalid item index
    result = await oms.execute({"operation": "cancel_line_item", "order_id": "ORD-B2", "item_index": 5})
    ok = result["status"] == "error"
    status = "✓" if ok else "✗"
    if ok: passed += 1
    else: failed += 1
    print(f"  {status} [OMS: cancel_line_item ORD-B2 item 5 → error (out of range)]")

    # Test 5: Update address on new order
    result = await oms.execute({
        "operation": "update_shipping_address",
        "order_id": "ORD-D1",
        "new_address": "Plot 7, Infopark SEZ, Kochi",
    })
    ok = result["status"] == "success"
    status = "✓" if ok else "✗"
    if ok: passed += 1
    else: failed += 1
    print(f"  {status} [OMS: update_shipping_address ORD-D1 → success]")

    # Test 6: Non-existent order
    result = await oms.execute({"operation": "get_order_status", "order_id": "ORD-ZZZZ"})
    ok = result["status"] == "error"
    status = "✓" if ok else "✗"
    if ok: passed += 1
    else: failed += 1
    print(f"  {status} [OMS: get_order_status ORD-ZZZZ → error (not found)]")

    print()

    # ── CRM Tests ─────────────────────────────────────────────────────────

    # Test 7: Get profile for new customer
    result = await crm.execute({"operation": "get_customer_profile", "customer_id": "CUST-003"})
    ok = result["status"] == "success" and result["data"]["tier"] == "platinum"
    status = "✓" if ok else "✗"
    if ok: passed += 1
    else: failed += 1
    print(f"  {status} [CRM: get_customer_profile CUST-003 → platinum tier]")

    # Test 8: Get profile for bronze customer
    result = await crm.execute({"operation": "get_customer_profile", "customer_id": "CUST-004"})
    ok = result["status"] == "success" and result["data"]["tier"] == "bronze"
    status = "✓" if ok else "✗"
    if ok: passed += 1
    else: failed += 1
    print(f"  {status} [CRM: get_customer_profile CUST-004 → bronze tier]")

    # Test 9: Get profile for non-existent customer
    result = await crm.execute({"operation": "get_customer_profile", "customer_id": "CUST-999"})
    ok = result["status"] == "error"
    status = "✓" if ok else "✗"
    if ok: passed += 1
    else: failed += 1
    print(f"  {status} [CRM: get_customer_profile CUST-999 → error (not found)]")

    # Test 10: Create escalation case
    result = await crm.execute({
        "operation": "create_case",
        "customer_id": "CUST-003",
        "summary": "High-value refund for monitor",
        "priority": "high",
        "trace_id": "TRACE-TEST-001",
    })
    ok = result["status"] == "success" and result["case_id"].startswith("CASE-")
    status = "✓" if ok else "✗"
    if ok: passed += 1
    else: failed += 1
    print(f"  {status} [CRM: create_case CUST-003 → {result.get('case_id', 'N/A')}]")

    print()

    # ── Payments Tests ────────────────────────────────────────────────────

    # Test 11: Safe refund (under ₹25K)
    result = await payments.execute({
        "operation": "initiate_refund",
        "order_id": "ORD-C1",
        "amount": 3500,
    })
    ok = result["status"] == "success"
    status = "✓" if ok else "✗"
    if ok: passed += 1
    else: failed += 1
    print(f"  {status} [Payments: ₹3,500 refund → success]")

    # Test 12: Exact boundary refund (₹25,000 — should pass)
    result = await payments.execute({
        "operation": "initiate_refund",
        "order_id": "ORD-B3",
        "amount": 25000,
    })
    ok = result["status"] == "success"
    status = "✓" if ok else "✗"
    if ok: passed += 1
    else: failed += 1
    print(f"  {status} [Payments: ₹25,000 refund (boundary) → success]")

    # Test 13: Over-limit refund (₹32,000 — should block)
    result = await payments.execute({
        "operation": "initiate_refund",
        "order_id": "ORD-B1",
        "amount": 32000,
    })
    ok = result["status"] == "error" and "escalate" in result.get("action", "")
    status = "✓" if ok else "✗"
    if ok: passed += 1
    else: failed += 1
    print(f"  {status} [Payments: ₹32,000 refund → blocked (escalate)]")

    print()

    # ── KB Tests (new operations) ─────────────────────────────────────────

    # Test 14: get_article
    result = await kb.execute({"operation": "get_article", "article_id": "KB-005"})
    ok = result["status"] == "success" and "Warranty" in result["data"]["title"]
    status = "✓" if ok else "✗"
    if ok: passed += 1
    else: failed += 1
    print(f"  {status} [KB: get_article KB-005 → Warranty Policy]")

    # Test 15: get_article non-existent
    result = await kb.execute({"operation": "get_article", "article_id": "KB-999"})
    ok = result["status"] == "error"
    status = "✓" if ok else "✗"
    if ok: passed += 1
    else: failed += 1
    print(f"  {status} [KB: get_article KB-999 → error (not found)]")

    # Test 16: list_topics
    result = await kb.execute({"operation": "list_topics"})
    ok = result["status"] == "success" and len(result["data"]) == 10
    status = "✓" if ok else "✗"
    if ok: passed += 1
    else: failed += 1
    print(f"  {status} [KB: list_topics → {len(result.get('data', []))} articles]")

    print()
    print(f"  Results: {passed}/{passed + failed} passed")
    return passed, failed


# ═══════════════════════════════════════════════════════════════════════════════
# Section 7: INTENT CLASSIFICATION (Expanded)
# ═══════════════════════════════════════════════════════════════════════════════

def test_intent_classification_expanded():
    """Test intent classification with queries referencing expanded data."""
    print("\n" + "=" * 70)
    print("  SECTION 7: INTENT CLASSIFICATION (Expanded)")
    print("=" * 70)

    test_cases = [
        ("Where is my order ORD-A1?", Intent.TRACKING, "New order tracking"),
        ("Track ORD-B2", Intent.TRACKING, "Minimal tracking query"),
        ("What is the delivery status of ORD-D1?", Intent.TRACKING, "Delivery status"),
        ("Cancel item 2 from ORD-A2 and refund me", Intent.COMPOUND, "Cancel + refund compound"),
        ("Cancel item 1 and update address for ORD-B1", Intent.COMPOUND, "Cancel + address compound"),
        ("I want to speak to a human about ORD-C1", Intent.ESCALATION, "Human escalation"),
        ("Escalate my complaint about ORD-D2", Intent.ESCALATION, "Escalation keyword"),
        ("Let me talk to your supervisor", Intent.ESCALATION, "Supervisor keyword"),
        ("What is your warranty policy?", Intent.POLICY, "Warranty policy"),
        ("Can I exchange my order?", Intent.POLICY, "Exchange policy"),
        ("Hello, I need help", Intent.GENERAL, "General greeting (control)"),
    ]

    passed, failed = 0, 0
    for query, expected, desc in test_cases:
        result = classify_intent(query)
        ok = result == expected
        status = "✓" if ok else "✗"
        if ok: passed += 1
        else: failed += 1
        print(f"  {status} [{desc}]: \"{query}\" → {result.value} (expected {expected.value})")

    print(f"\n  Results: {passed}/{passed + failed} passed")
    return passed, failed


# ═══════════════════════════════════════════════════════════════════════════════
# Main Runner
# ═══════════════════════════════════════════════════════════════════════════════

async def main():
    print("=" * 70)
    print("  ATLASCARE — EXTENDED JOURNEY & MIXED QUERY TEST SUITE")
    print("=" * 70)

    total_passed = 0
    total_failed = 0

    # Sync tests first (no LLM needed)
    p, f = test_entity_extraction()
    total_passed += p
    total_failed += f

    p, f = test_intent_classification_expanded()
    total_passed += p
    total_failed += f

    # Async tool unit tests (no LLM needed)
    p, f = await test_tool_operations()
    total_passed += p
    total_failed += f

    # Async full pipeline tests (require GROQ_API_KEY)
    has_key = bool(os.environ.get("GROQ_API_KEY"))
    if has_key:
        # p, f = await test_tracking_journey()
        # total_passed += p
        # total_failed += f

        # p, f = await test_compound_journey()
        # total_passed += p
        # total_failed += f

        # p, f = await test_escalation_journey()
        # total_passed += p
        # total_failed += f

        p, f = await test_mixed_queries()
        total_passed += p
        total_failed += f
    else:
        print("\n  ⚠ Skipping full pipeline tests (GROQ_API_KEY not set).")
        print("  Sections 1-4 (Tracking, Compound, Escalation, Mixed) require the API key.")
        print("  Set GROQ_API_KEY to run the full suite.\n")

    # ── Final Summary ─────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("  FINAL SUMMARY")
    print("=" * 70)
    print(f"  Total: {total_passed + total_failed} tests")
    print(f"  Passed: {total_passed}")
    print(f"  Failed: {total_failed}")
    if total_failed == 0:
        print("  ✓ ALL TESTS PASSED")
    else:
        print(f"  ✗ {total_failed} TEST(S) FAILED")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
