"""
Custom Query Test - Full trace and log output for compound request.

Tests the query:
  "Cancel item 2 from order ORD-J2, refund it to my HDFC card,
   and ship the other two items to my office address instead."
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

from agent.orchestrator import handle_query
from agent import _trace_store


async def run_test():
    print("=" * 70)
    print("  ATLASCARE -- CUSTOM QUERY TEST")
    print("=" * 70)

    query = (
        "Cancel item 2 from order ORD-J2, refund it to my HDFC card, "
        "and ship the other two items to my office address instead."
    )
    # Note: Using ORD-J2 because ORD-XXXXX doesn't exist in orders.json.
    # ORD-J2 has 2 items (Laptop + Mouse), so item 2 = Mouse.

    session_id = "custom-test-session-001"
    customer_id = "CUST-001"

    print(f"\n[QUERY]")
    print(f'   "{query}"\n')
    print(f"   Session ID : {session_id}")
    print(f"   Customer ID: {customer_id}")
    print("-" * 70)

    # Run the query through the full pipeline
    response = await handle_query(query, session_id, customer_id)

    # -- Agent Response --
    print("\n[AGENT RESPONSE]")
    print("-" * 70)
    print(response.response)
    print("-" * 70)

    # -- Trace Info (from API response) --
    trace = response.trace.model_dump()
    print("\n[TRACE INFO - API Response]")
    print("-" * 70)
    print(json.dumps(trace, indent=2, default=str))

    # -- Enriched Trace (from internal store) --
    trace_id = trace["trace_id"]
    enriched_trace = _trace_store.get(trace_id, {})
    if enriched_trace:
        print("\n[ENRICHED TRACE - Internal Store]")
        print("-" * 70)
        print(json.dumps(enriched_trace, indent=2, default=str))

    # -- Summary --
    print("\n" + "=" * 70)
    print("  SUMMARY")
    print("=" * 70)
    print(f"  Trace ID       : {trace_id}")
    print(f"  Session ID     : {trace['session_id']}")
    print(f"  Latency        : {trace['latency_ms']} ms")
    print(f"  Tool Calls     : {len(trace['tool_calls'])}")
    for i, tc in enumerate(trace["tool_calls"], 1):
        print(f"    [{i}] {tc['tool']}.{tc['params'].get('operation', '?')} -> {tc['result']}")
    print(f"  Policy Violations: {trace.get('policy_violations', [])}")
    print(f"  Retry Counts   : {trace.get('retry_counts', {})}")

    # Node transitions if available
    if enriched_trace:
        transitions = enriched_trace.get("node_transitions", [])
        latencies = enriched_trace.get("node_latencies", {})
        if transitions:
            print(f"\n  Node Path: {' -> '.join(transitions)}")
        if latencies:
            print(f"  Node Latencies:")
            for node, ms in latencies.items():
                print(f"    {node}: {ms} ms")

    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(run_test())
