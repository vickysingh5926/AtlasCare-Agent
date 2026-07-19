"""
KB / Policy Query Test Suite

Tests knowledge base query handling across the full pipeline:
- Simple policy queries
- Paraphrased/synonym queries
- Damaged item queries
- Warranty queries
- Mixed intent (tracking + policy)
- No-match graceful handling
- Intent classification accuracy
- KB search scoring and ranking
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

from agent.intent import classify_intent, Intent
from tools.kb import KBTool, _keyword_match, _load_kb, _expand_query_with_synonyms


# ── Section 1: Intent Classification Tests ────────────────────────────────────

def test_intent_classification():
    """Test that various policy-related queries are classified as POLICY intent."""
    print("\n" + "=" * 70)
    print("  SECTION 1: INTENT CLASSIFICATION")
    print("=" * 70)

    test_cases = [
        # (query, expected_intent, description)
        ("What is your return policy?", Intent.POLICY, "Explicit 'return policy'"),
        ("What is the refund policy?", Intent.POLICY, "Explicit 'refund policy'"),
        ("How long do I have to return an item?", Intent.POLICY, "How long to return"),
        ("Can I return a product after 20 days?", Intent.POLICY, "Can I return"),
        ("Can I exchange this for a different size?", Intent.POLICY, "Can I exchange"),
        ("What are the shipping rules?", Intent.POLICY, "Rules keyword"),
        ("Do you have a warranty on electronics?", Intent.POLICY, "Warranty keyword"),
        ("I received a broken laptop, what can I do?", Intent.POLICY, "Broken/damaged item"),
        ("What is the cancellation policy?", Intent.POLICY, "What is + cancellation"),
        ("How do I return a defective product?", Intent.POLICY, "How do I return"),
        ("Can I get my money back?", Intent.POLICY, "Money back synonym"),
        ("FAQ about returns", Intent.POLICY, "FAQ keyword"),
        ("Am I eligible for a refund?", Intent.POLICY, "Eligible keyword"),
        ("Where is my order ORD-J1?", Intent.TRACKING, "Tracking (control case)"),
        ("Cancel item 2 and refund me", Intent.COMPOUND, "Compound (control case)"),
    ]

    passed = 0
    failed = 0
    for query, expected, description in test_cases:
        result = classify_intent(query)
        status = "✓" if result == expected else "✗"
        if result == expected:
            passed += 1
        else:
            failed += 1
        print(f"  {status} [{description}]")
        print(f"    Query:    \"{query}\"")
        print(f"    Expected: {expected.value}, Got: {result.value}")
        if result != expected:
            print(f"    *** MISMATCH ***")
        print()

    print(f"  Results: {passed}/{passed + failed} passed")
    return passed, failed


# ── Section 2: KB Search Tests ────────────────────────────────────────────────

def test_kb_search():
    """Test that KB search returns relevant articles for various queries."""
    print("\n" + "=" * 70)
    print("  SECTION 2: KB SEARCH (Keyword Matching + Synonyms)")
    print("=" * 70)

    kb_data = _load_kb()
    articles = kb_data.get("articles", [])

    test_cases = [
        # (query, expected_article_ids, description)
        (
            "What is your return policy?",
            ["KB-002"],
            "Direct return policy query",
        ),
        (
            "refund threshold rules",
            ["KB-001"],
            "Direct refund threshold query",
        ),
        (
            "Can I get my money back?",
            ["KB-001"],
            "Synonym: money back → refund",
        ),
        (
            "How many days to send something back?",
            ["KB-002"],
            "Synonym: send back → return",
        ),
        (
            "I received a broken laptop",
            ["KB-008"],
            "Damaged item query",
        ),
        (
            "Does this have a warranty?",
            ["KB-005"],
            "Warranty query",
        ),
        (
            "What payment methods do you accept?",
            ["KB-006"],
            "Payment methods query",
        ),
        (
            "How long does shipping take?",
            ["KB-007"],
            "Shipping query",
        ),
        (
            "How do I contact support?",
            ["KB-009"],
            "Contact info query",
        ),
        (
            "Can I exchange for a different size?",
            ["KB-010"],
            "Exchange query",
        ),
        (
            "What is the escalation SLA?",
            ["KB-003"],
            "Escalation SLA query",
        ),
        (
            "Can I cancel part of my order?",
            ["KB-004"],
            "Partial cancellation query",
        ),
    ]

    passed = 0
    failed = 0
    for query, expected_ids, description in test_cases:
        results = _keyword_match(query, articles)
        result_ids = [a.get("article_id") for a in results]

        # Check if the expected article is in top results (top 3)
        top_ids = result_ids[:3]
        match = all(eid in top_ids for eid in expected_ids)

        status = "✓" if match else "✗"
        if match:
            passed += 1
        else:
            failed += 1

        print(f"  {status} [{description}]")
        print(f"    Query:    \"{query}\"")
        print(f"    Expected: {expected_ids} in top 3")
        print(f"    Got top3: {top_ids}")
        if not match:
            print(f"    All results: {result_ids}")
            print(f"    *** EXPECTED ARTICLE NOT IN TOP 3 ***")
        print()

    print(f"  Results: {passed}/{passed + failed} passed")
    return passed, failed


# ── Section 3: Synonym Expansion Tests ────────────────────────────────────────

def test_synonym_expansion():
    """Test that synonym expansion correctly maps paraphrases to canonical terms."""
    print("\n" + "=" * 70)
    print("  SECTION 3: SYNONYM EXPANSION")
    print("=" * 70)

    test_cases = [
        # (query, expected_expansions, description)
        ("Can I get my money back?", ["refund"], "money back → refund"),
        ("I want to send back this item", ["return"], "send back → return"),
        ("Is there a guarantee on this?", ["warranty"], "guarantee → warranty"),
        ("The product is not working", ["damaged"], "not working → damaged"),
        ("I paid via cash on delivery", ["payment"], "cash on delivery → payment"),
        ("I want to talk to a manager", ["escalation"], "manager → escalation"),
    ]

    passed = 0
    failed = 0
    for query, expected_expansions, description in test_cases:
        expanded = _expand_query_with_synonyms(query)

        match = all(exp in expanded for exp in expected_expansions)
        status = "✓" if match else "✗"
        if match:
            passed += 1
        else:
            failed += 1

        print(f"  {status} [{description}]")
        print(f"    Query:    \"{query}\"")
        print(f"    Expected expansions: {expected_expansions}")
        print(f"    Got: {expanded}")
        if not match:
            print(f"    *** MISSING EXPANSION ***")
        print()

    print(f"  Results: {passed}/{passed + failed} passed")
    return passed, failed


# ── Section 4: Edge Cases ─────────────────────────────────────────────────────

def test_edge_cases():
    """Test graceful handling of edge cases."""
    print("\n" + "=" * 70)
    print("  SECTION 4: EDGE CASES")
    print("=" * 70)

    kb_data = _load_kb()
    articles = kb_data.get("articles", [])

    passed = 0
    failed = 0

    # Test 1: No-match query
    results = _keyword_match("What is your pet policy?", articles)
    match = len(results) == 0 or all(
        "pet" not in a.get("content", "").lower() for a in results
    )
    status = "✓" if match else "✗"
    if match:
        passed += 1
    else:
        failed += 1
    print(f"  {status} [No-match: 'pet policy']")
    print(f"    Results: {len(results)} articles (expected 0 or irrelevant)")
    print()

    # Test 2: Empty query
    results = _keyword_match("", articles)
    match = len(results) == 0
    status = "✓" if match else "✗"
    if match:
        passed += 1
    else:
        failed += 1
    print(f"  {status} [Empty query]")
    print(f"    Results: {len(results)} articles (expected 0)")
    print()

    # Test 3: Very short query
    results = _keyword_match("refund", articles)
    match = len(results) > 0
    status = "✓" if match else "✗"
    if match:
        passed += 1
    else:
        failed += 1
    print(f"  {status} [Single keyword: 'refund']")
    print(f"    Results: {len(results)} articles (expected > 0)")
    print()

    # Test 4: Query with order ID noise (should still find articles)
    results = _keyword_match("return policy for ORD-J1", articles)
    result_ids = [a.get("article_id") for a in results[:3]]
    match = "KB-002" in result_ids
    status = "✓" if match else "✗"
    if match:
        passed += 1
    else:
        failed += 1
    print(f"  {status} [Query with order ID noise: 'return policy for ORD-J1']")
    print(f"    Top 3: {result_ids} (expected KB-002 present)")
    print()

    print(f"  Results: {passed}/{passed + failed} passed")
    return passed, failed


# ── Section 5: Full Pipeline KB Test (async) ──────────────────────────────────

async def test_full_pipeline():
    """Test KB queries through the full agent pipeline."""
    print("\n" + "=" * 70)
    print("  SECTION 5: FULL PIPELINE (End-to-End)")
    print("=" * 70)

    from agent.orchestrator import handle_query

    test_cases = [
        (
            "What is your return policy?",
            "Simple policy query",
            ["kb"],  # expected tools used
        ),
        (
            "I received a damaged laptop, what can I do?",
            "Damaged item query",
            ["kb"],
        ),
        (
            "How long does shipping take?",
            "Shipping policy query",
            ["kb"],
        ),
    ]

    passed = 0
    failed = 0
    for query, description, expected_tools in test_cases:
        try:
            response = await handle_query(query, "kb-test-session", "CUST-001")

            # Check that response is non-empty
            has_response = bool(response.response and len(response.response) > 20)

            # Check that KB tool was called
            tools_used = [tc.tool for tc in response.trace.tool_calls]
            has_kb = any(t in tools_used for t in expected_tools)

            match = has_response and has_kb
            status = "✓" if match else "✗"
            if match:
                passed += 1
            else:
                failed += 1

            print(f"  {status} [{description}]")
            print(f"    Query:    \"{query}\"")
            print(f"    Response: \"{response.response[:120]}...\"")
            print(f"    Tools:    {tools_used}")
            print(f"    Latency:  {response.trace.latency_ms}ms")
            if not match:
                if not has_response:
                    print(f"    *** EMPTY/SHORT RESPONSE ***")
                if not has_kb:
                    print(f"    *** KB TOOL NOT CALLED (expected {expected_tools}) ***")
            print()

        except Exception as e:
            failed += 1
            print(f"  ✗ [{description}]")
            print(f"    Query: \"{query}\"")
            print(f"    ERROR: {e}")
            print()

    print(f"  Results: {passed}/{passed + failed} passed")
    return passed, failed


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    print("=" * 70)
    print("  ATLASCARE — KB/POLICY QUERY TEST SUITE")
    print("=" * 70)

    total_passed = 0
    total_failed = 0

    # Section 1: Intent classification (sync)
    p, f = test_intent_classification()
    total_passed += p
    total_failed += f

    # Section 2: KB search (sync)
    p, f = test_kb_search()
    total_passed += p
    total_failed += f

    # Section 3: Synonym expansion (sync)
    p, f = test_synonym_expansion()
    total_passed += p
    total_failed += f

    # Section 4: Edge cases (sync)
    p, f = test_edge_cases()
    total_passed += p
    total_failed += f

    # Section 5: Full pipeline (async, requires LLM)
    if os.environ.get("GROQ_API_KEY"):
        p, f = await test_full_pipeline()
        total_passed += p
        total_failed += f
    else:
        print("\n  ⚠ Skipping full pipeline tests (GROQ_API_KEY not found in .env).\n")

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
