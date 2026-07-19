"""
Comprehensive Manual Test Runner — All 15 Tests from Data Schemas & Testing Reference

Runs each test against the live server, verifies all expected outcomes,
and displays graph flow + latency for every test.
"""

import sys
import json
import time

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

import httpx

BASE = "http://127.0.0.1:8000"
PASS = "[PASS]"
FAIL = "[FAIL]"
results = []


def post_query(message: str, session_id: str) -> dict:
    """Send a query to the server and return parsed JSON."""
    r = httpx.post(
        f"{BASE}/query",
        json={"message": message, "session_id": session_id},
        timeout=60.0,
    )
    return r.status_code, r.json() if r.status_code == 200 else r.text


def check(label: str, condition: bool, detail: str = ""):
    tag = PASS if condition else FAIL
    msg = f"  {tag} {label}"
    if detail and not condition:
        msg += f"  --> {detail}"
    print(msg)
    return condition


def show_graph_and_latency(data: dict):
    trace = data.get("trace", {})

    # Graph flow from enriched trace
    # Try workflow_summary.node_path first, then node_spans
    node_path = []
    ws = trace.get("workflow_summary")
    if ws and ws.get("node_path"):
        node_path = ws["node_path"]
    elif trace.get("node_spans"):
        node_path = [s["node"] for s in trace["node_spans"]]

    if node_path:
        print(f"  Graph Flow : {' -> '.join(node_path)}")
    else:
        print(f"  Graph Flow : (not available in base trace)")

    # Per-node latencies
    spans = trace.get("node_spans", [])
    if spans:
        print(f"  Node Latencies:")
        for s in spans:
            bar = "#" * max(1, s["latency_ms"] // 100)
            print(f"    {s['node']:30s} {s['latency_ms']:>6d} ms  {bar}")

    # Total latency
    print(f"  Total Latency: {trace.get('latency_ms', '?')} ms")


def show_response(data: dict):
    response = data.get("response", "")
    if response:
        print("\n  LLM Response:")
        # Wrap response text nicely for readability
        import textwrap
        wrapped = textwrap.fill(response, width=65, initial_indent="    ", subsequent_indent="    ")
        print(wrapped)
        print()


def show_tool_calls(data: dict):
    trace = data.get("trace", {})
    tcs = trace.get("tool_calls", [])
    if tcs:
        print(f"  Tool Calls ({len(tcs)}):")
        for i, tc in enumerate(tcs, 1):
            op = tc["params"].get("operation", "?")
            print(f"    [{i}] {tc['tool']}.{op} -> {tc['result']}")
    else:
        print(f"  Tool Calls: (none)")


# ════════════════════════════════════════════════════════════════════════
# TEST 1: Simple Tracking (J1) - Fast Path
# ════════════════════════════════════════════════════════════════════════
def test_1():
    print("\n" + "=" * 70)
    print("TEST 1: Simple Tracking (J1) - Fast Path")
    print("=" * 70)
    code, data = post_query("Where is my order ORD-J1?", "manual-j1")
    passed = True

    passed &= check("HTTP 200", code == 200)
    if code != 200:
        results.append(("Test 1: Simple Tracking", False))
        return

    trace = data["trace"]
    tcs = trace["tool_calls"]

    passed &= check("Has tool_calls", len(tcs) >= 1)
    passed &= check("First tool is 'oms'", tcs[0]["tool"] == "oms" if tcs else False)
    passed &= check("Operation is 'get_order_status'",
                     tcs[0]["params"].get("operation") == "get_order_status" if tcs else False)
    passed &= check("Result is 'success'", tcs[0]["result"] == "success" if tcs else False)

    resp_lower = data["response"].lower()
    passed &= check("Response mentions 'shipped'", "shipped" in resp_lower or "ship" in resp_lower)
    passed &= check("Response mentions tracking number",
                     "track-7x9k2m" in resp_lower or "track" in resp_lower)

    show_tool_calls(data)
    show_graph_and_latency(data)
    show_response(data)
    results.append(("Test 1: Simple Tracking (J1)", passed))


# ════════════════════════════════════════════════════════════════════════
# TEST 2: Compound Request (J2) - Cancel + Refund + Address Update
# ════════════════════════════════════════════════════════════════════════
def test_2():
    print("\n" + "=" * 70)
    print("TEST 2: Compound Request (J2) - Cancel + Refund + Address Update")
    print("=" * 70)
    code, data = post_query(
        "Cancel my order ORD-J2 item 1, refund me 85000, and update my address to New Address.",
        "manual-j2"
    )
    passed = True
    passed &= check("HTTP 200", code == 200)
    if code != 200:
        results.append(("Test 2: Compound (J2)", False))
        return

    trace = data["trace"]
    tcs = trace["tool_calls"]
    tools_used = [(tc["tool"], tc["params"].get("operation", "")) for tc in tcs]

    passed &= check("OMS cancel_line_item present",
                     ("oms", "cancel_line_item") in tools_used)
    passed &= check("CRM create_case present (escalation)",
                     ("crm", "create_case") in tools_used)
    passed &= check("OMS update_shipping_address present",
                     ("oms", "update_shipping_address") in tools_used)
    passed &= check("NO payments initiate_refund in trace",
                     ("payments", "initiate_refund") not in tools_used)

    show_tool_calls(data)
    show_graph_and_latency(data)
    show_response(data)
    results.append(("Test 2: Compound (J2)", passed))


# ════════════════════════════════════════════════════════════════════════
# TEST 3: Escalation (J3) - Refund Exceeds Limit
# ════════════════════════════════════════════════════════════════════════
def test_3():
    print("\n" + "=" * 70)
    print("TEST 3: Escalation (J3) - Refund Exceeds Limit")
    print("=" * 70)
    code, data = post_query("Cancel order ORD-J3 and refund me 42000.", "manual-j3")
    passed = True
    passed &= check("HTTP 200", code == 200)
    if code != 200:
        results.append(("Test 3: Escalation (J3)", False))
        return

    trace = data["trace"]
    tcs = trace["tool_calls"]
    tools_used = [(tc["tool"], tc["params"].get("operation", "")) for tc in tcs]

    passed &= check("OMS cancel present", ("oms", "cancel_line_item") in tools_used)
    passed &= check("CRM create_case present", ("crm", "create_case") in tools_used)
    passed &= check("NO payments call", ("payments", "initiate_refund") not in tools_used)

    # Check CRM case has trace_id
    crm_calls = [tc for tc in tcs if tc["tool"] == "crm" and tc["params"].get("operation") == "create_case"]
    if crm_calls:
        passed &= check("CRM case has trace_id linkage",
                         bool(crm_calls[0].get("data", {}).get("trace_id", "")))

    passed &= check("policy_violations is non-empty",
                     len(trace.get("policy_violations", [])) > 0)

    show_tool_calls(data)
    show_graph_and_latency(data)
    show_response(data)
    results.append(("Test 3: Escalation (J3)", passed))


# ════════════════════════════════════════════════════════════════════════
# TEST 4: Policy Lookup (J4) - Fast Path
# ════════════════════════════════════════════════════════════════════════
def test_4():
    print("\n" + "=" * 70)
    print("TEST 4: Policy Lookup (J4) - Fast Path")
    print("=" * 70)
    code, data = post_query("What is your return policy?", "manual-j4")
    passed = True
    passed &= check("HTTP 200", code == 200)
    if code != 200:
        results.append(("Test 4: Policy (J4)", False))
        return

    trace = data["trace"]
    tcs = trace["tool_calls"]
    tools_used = [(tc["tool"], tc["params"].get("operation", "")) for tc in tcs]

    passed &= check("KB search_policy present", ("kb", "search_policy") in tools_used)

    resp_lower = data["response"].lower()
    passed &= check("Response mentions return/30 days",
                     "30" in resp_lower or "return" in resp_lower)

    show_tool_calls(data)
    show_graph_and_latency(data)
    show_response(data)
    results.append(("Test 4: Policy Lookup (J4)", passed))


# ════════════════════════════════════════════════════════════════════════
# TEST 5: Safe Refund (<=25K) - Should Auto-Process
# ════════════════════════════════════════════════════════════════════════
def test_5():
    print("\n" + "=" * 70)
    print("TEST 5: Safe Refund (Rs.1,000) - Should Auto-Process")
    print("=" * 70)
    code, data = post_query(
        "Cancel item 1 from order ORD-J1 and refund me 1000.",
        "manual-safe-refund"
    )
    passed = True
    passed &= check("HTTP 200", code == 200)
    if code != 200:
        results.append(("Test 5: Safe Refund", False))
        return

    trace = data["trace"]
    tcs = trace["tool_calls"]
    tools_used = [(tc["tool"], tc["params"].get("operation", "")) for tc in tcs]

    has_payments = ("payments", "initiate_refund") in tools_used
    passed &= check("Payments initiate_refund present", has_payments)

    if has_payments:
        pay_call = [tc for tc in tcs if tc["tool"] == "payments"][0]
        passed &= check("Payments result is 'success'", pay_call["result"] == "success")

    passed &= check("NO CRM escalation",
                     ("crm", "create_case") not in tools_used)

    show_tool_calls(data)
    show_graph_and_latency(data)
    show_response(data)
    results.append(("Test 5: Safe Refund (Rs.1K)", passed))


# ════════════════════════════════════════════════════════════════════════
# TEST 6: Boundary Refund (Exactly Rs.25,000) - Should NOT Be Blocked
# ════════════════════════════════════════════════════════════════════════
def test_6():
    print("\n" + "=" * 70)
    print("TEST 6: Boundary Refund (Rs.25,000 exactly) - Should NOT Be Blocked")
    print("=" * 70)
    code, data = post_query(
        "Cancel item 1 from order ORD-J1 and refund me 25000.",
        "manual-boundary"
    )
    passed = True
    passed &= check("HTTP 200", code == 200)
    if code != 200:
        results.append(("Test 6: Boundary Rs.25K", False))
        return

    trace = data["trace"]
    tcs = trace["tool_calls"]
    tools_used = [(tc["tool"], tc["params"].get("operation", "")) for tc in tcs]

    has_payments = ("payments", "initiate_refund") in tools_used
    passed &= check("Payments call present (not blocked)", has_payments)
    passed &= check("NO CRM escalation",
                     ("crm", "create_case") not in tools_used)

    show_tool_calls(data)
    show_graph_and_latency(data)
    show_response(data)
    results.append(("Test 6: Boundary Rs.25K", passed))


# ════════════════════════════════════════════════════════════════════════
# TEST 7: Boundary Refund (Rs.25,001) - Should Be Blocked
# ════════════════════════════════════════════════════════════════════════
def test_7():
    print("\n" + "=" * 70)
    print("TEST 7: Boundary Refund (Rs.25,001) - Should Be BLOCKED")
    print("=" * 70)
    code, data = post_query(
        "Cancel item 1 from order ORD-J1 and refund me 25001.",
        "manual-boundary-over"
    )
    passed = True
    passed &= check("HTTP 200", code == 200)
    if code != 200:
        results.append(("Test 7: Boundary Rs.25,001", False))
        return

    trace = data["trace"]
    tcs = trace["tool_calls"]
    tools_used = [(tc["tool"], tc["params"].get("operation", "")) for tc in tcs]

    passed &= check("NO payments initiate_refund",
                     ("payments", "initiate_refund") not in tools_used)
    passed &= check("CRM escalation case created",
                     ("crm", "create_case") in tools_used)

    show_tool_calls(data)
    show_graph_and_latency(data)
    show_response(data)
    results.append(("Test 7: Boundary Rs.25,001", passed))


# ════════════════════════════════════════════════════════════════════════
# TEST 8: Item 2 Cancellation from Multi-Item Order
# ════════════════════════════════════════════════════════════════════════
def test_8():
    print("\n" + "=" * 70)
    print("TEST 8: Item 2 Cancellation from ORD-J2 (Mouse)")
    print("=" * 70)
    code, data = post_query("Cancel item 2 from order ORD-J2.", "manual-item2")
    passed = True
    passed &= check("HTTP 200", code == 200)
    if code != 200:
        results.append(("Test 8: Item 2 Cancel", False))
        return

    trace = data["trace"]
    tcs = trace["tool_calls"]

    oms_cancel = [tc for tc in tcs if tc["tool"] == "oms" and tc["params"].get("operation") == "cancel_line_item"]
    passed &= check("OMS cancel_line_item present", len(oms_cancel) >= 1)

    if oms_cancel:
        passed &= check("item_index is 2", oms_cancel[0]["params"].get("item_index") == 2)

    resp_lower = data["response"].lower()
    passed &= check("Response mentions 'mouse'", "mouse" in resp_lower)

    show_tool_calls(data)
    show_graph_and_latency(data)
    show_response(data)
    results.append(("Test 8: Item 2 Cancel", passed))


# ════════════════════════════════════════════════════════════════════════
# TEST 9: Address Update Only
# ════════════════════════════════════════════════════════════════════════
def test_9():
    print("\n" + "=" * 70)
    print("TEST 9: Address Update Only (ORD-J2)")
    print("=" * 70)
    code, data = post_query(
        "Update shipping address for order ORD-J2 to 4th Floor, Prestige Tower, Outer Ring Road, Bengaluru 560103.",
        "manual-address"
    )
    passed = True
    passed &= check("HTTP 200", code == 200)
    if code != 200:
        results.append(("Test 9: Address Update", False))
        return

    trace = data["trace"]
    tcs = trace["tool_calls"]
    tools_used = [(tc["tool"], tc["params"].get("operation", "")) for tc in tcs]

    passed &= check("OMS update_shipping_address present",
                     ("oms", "update_shipping_address") in tools_used)

    show_tool_calls(data)
    show_graph_and_latency(data)
    show_response(data)
    results.append(("Test 9: Address Update", passed))


# ════════════════════════════════════════════════════════════════════════
# TEST 10: Invalid Order ID - Graceful Error
# ════════════════════════════════════════════════════════════════════════
def test_10():
    print("\n" + "=" * 70)
    print("TEST 10: Invalid Order ID (ORD-INVALID)")
    print("=" * 70)
    code, data = post_query("Where is my order ORD-INVALID?", "manual-invalid")
    passed = True
    passed &= check("HTTP 200 (graceful, no crash)", code == 200)
    if code != 200:
        results.append(("Test 10: Invalid Order", False))
        return

    resp_lower = data["response"].lower()
    passed &= check("Response acknowledges issue",
                     "not found" in resp_lower or "unable" in resp_lower
                     or "couldn" in resp_lower or "sorry" in resp_lower
                     or "don't" in resp_lower or "cannot" in resp_lower
                     or "error" in resp_lower or "invalid" in resp_lower)

    show_tool_calls(data)
    show_graph_and_latency(data)
    show_response(data)
    results.append(("Test 10: Invalid Order", passed))


# ════════════════════════════════════════════════════════════════════════
# TEST 11: Empty Query - 400 Rejection
# ════════════════════════════════════════════════════════════════════════
def test_11():
    print("\n" + "=" * 70)
    print("TEST 11: Empty Query - Should Return 400")
    print("=" * 70)
    r = httpx.post(
        f"{BASE}/query",
        json={"message": "   ", "session_id": "manual-empty"},
        timeout=30.0,
    )
    passed = True
    passed &= check("HTTP 400 Bad Request", r.status_code == 400,
                     f"Got {r.status_code} instead")
    print(f"  Response: {r.text[:200]}")
    results.append(("Test 11: Empty Query 400", passed))


# ════════════════════════════════════════════════════════════════════════
# TEST 12: Health Check
# ════════════════════════════════════════════════════════════════════════
def test_12():
    print("\n" + "=" * 70)
    print("TEST 12: Health Check Endpoint")
    print("=" * 70)
    r = httpx.get(f"{BASE}/health", timeout=10.0)
    passed = True
    passed &= check("HTTP 200", r.status_code == 200)
    body = r.json()
    passed &= check("status is 'healthy'", body.get("status") == "healthy")
    print(f"  Response: {json.dumps(body)}")
    results.append(("Test 12: Health Check", passed))


# ════════════════════════════════════════════════════════════════════════
# TEST 13: Trace Retrieval
# ════════════════════════════════════════════════════════════════════════
def test_13():
    print("\n" + "=" * 70)
    print("TEST 13: Trace Retrieval (GET /trace/:id)")
    print("=" * 70)

    # First, create a trace by running a simple query
    code, data = post_query("Where is my order ORD-J1?", "trace-retrieval-test")
    passed = True
    passed &= check("Setup query returns 200", code == 200)
    if code != 200:
        results.append(("Test 13: Trace Retrieval", False))
        return

    trace_id = data["trace"]["trace_id"]
    print(f"  Trace ID created: {trace_id}")

    # Now retrieve the trace
    r = httpx.get(f"{BASE}/trace/{trace_id}", timeout=10.0)
    passed &= check("GET /trace returns 200", r.status_code == 200)

    if r.status_code == 200:
        trace_data = r.json()
        passed &= check("Retrieved trace has matching trace_id",
                         trace_data.get("trace_id") == trace_id)
        passed &= check("Retrieved trace has tool_calls",
                         "tool_calls" in trace_data)
        passed &= check("Retrieved trace has node_spans",
                         "node_spans" in trace_data)

    # Also test 404 for non-existent trace
    r404 = httpx.get(f"{BASE}/trace/non-existent-id", timeout=10.0)
    passed &= check("Non-existent trace returns 404", r404.status_code == 404)

    show_response(data)
    results.append(("Test 13: Trace Retrieval", passed))


# ════════════════════════════════════════════════════════════════════════
# TEST 14: Escalation Keywords - "Talk to a manager"
# ════════════════════════════════════════════════════════════════════════
def test_14():
    print("\n" + "=" * 70)
    print("TEST 14: Escalation Keywords - 'Talk to a manager'")
    print("=" * 70)
    code, data = post_query(
        "I want to talk to a manager about my order ORD-J1.",
        "manual-escalate"
    )
    passed = True
    passed &= check("HTTP 200", code == 200)
    if code != 200:
        results.append(("Test 14: Escalation Keywords", False))
        return

    trace = data["trace"]
    tcs = trace["tool_calls"]
    tools_used = [(tc["tool"], tc["params"].get("operation", "")) for tc in tcs]

    passed &= check("CRM create_case present",
                     ("crm", "create_case") in tools_used)

    resp_lower = data["response"].lower()
    passed &= check("Response acknowledges escalation",
                     "escalat" in resp_lower or "case" in resp_lower
                     or "specialist" in resp_lower or "manager" in resp_lower
                     or "support" in resp_lower or "team" in resp_lower)

    show_tool_calls(data)
    show_graph_and_latency(data)
    show_response(data)
    results.append(("Test 14: Escalation Keywords", passed))


# ════════════════════════════════════════════════════════════════════════
# TEST 15: Refund Policy Specific Query
# ════════════════════════════════════════════════════════════════════════
def test_15():
    print("\n" + "=" * 70)
    print("TEST 15: Refund Policy Query")
    print("=" * 70)
    code, data = post_query(
        "What is the refund threshold limit?",
        "manual-refund-policy"
    )
    passed = True
    passed &= check("HTTP 200", code == 200)
    if code != 200:
        results.append(("Test 15: Refund Policy", False))
        return

    trace = data["trace"]
    tcs = trace["tool_calls"]
    tools_used = [(tc["tool"], tc["params"].get("operation", "")) for tc in tcs]

    passed &= check("KB search_policy present",
                     ("kb", "search_policy") in tools_used)

    resp_lower = data["response"].lower()
    passed &= check("Response mentions 25,000 or 25000",
                     "25,000" in resp_lower or "25000" in resp_lower or "25k" in resp_lower)

    show_tool_calls(data)
    show_graph_and_latency(data)
    show_response(data)
    results.append(("Test 15: Refund Policy", passed))


# ════════════════════════════════════════════════════════════════════════
# MAIN — Run All Tests
# ════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 70)
    print("  ATLASCARE -- COMPREHENSIVE MANUAL TEST SUITE")
    print(f"  Server: {BASE}")
    print("=" * 70)

    # Check server is up
    try:
        r = httpx.get(f"{BASE}/health", timeout=5.0)
        if r.status_code != 200:
            print("ERROR: Server is not healthy!")
            sys.exit(1)
        print("Server is healthy. Running all 15 tests...\n")
    except Exception as e:
        print(f"ERROR: Cannot connect to server at {BASE}: {e}")
        sys.exit(1)

    all_tests = [
        test_1, test_2, test_3, test_4, test_5,
        test_6, test_7, test_8, test_9, test_10,
        test_11, test_12, test_13, test_14, test_15,
    ]

    start = time.time()
    for test_fn in all_tests:
        try:
            test_fn()
        except Exception as e:
            print(f"  [ERROR] Test crashed: {e}")
            results.append((test_fn.__name__, False))

    elapsed = time.time() - start

    # ── Final Report ──────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("  FINAL REPORT")
    print("=" * 70)

    total = len(results)
    passed_count = sum(1 for _, p in results if p)
    failed_count = total - passed_count

    for name, passed in results:
        tag = PASS if passed else FAIL
        print(f"  {tag} {name}")

    print("-" * 70)
    print(f"  Total: {total}  |  Passed: {passed_count}  |  Failed: {failed_count}")
    print(f"  Total Execution Time: {elapsed:.1f}s")
    print("=" * 70)
