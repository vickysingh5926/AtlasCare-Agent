import sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

import httpx
import time

print("=" * 50)
print("  J1 Speed Test (with fast 8B model for synthesis)")
print("=" * 50)

# Run 3 times to get a reliable average
latencies = []
for i in range(3):
    t0 = time.time()
    r = httpx.post(
        "http://127.0.0.1:8000/query",
        json={"message": "Where is my order ORD-J1?", "session_id": f"speed-test-{i}"},
        timeout=30,
    )
    wall = (time.time() - t0) * 1000
    d = r.json()
    trace_ms = d["trace"]["latency_ms"]
    latencies.append(trace_ms)
    print(f"\n  Run {i+1}:")
    print(f"    Wall-clock: {wall:.0f} ms")
    print(f"    Trace latency: {trace_ms} ms")
    print(f"    Response: {d['response'][:120]}...")

print(f"\n  Average trace latency: {sum(latencies) / len(latencies):.0f} ms")
print(f"  Min: {min(latencies)} ms  |  Max: {max(latencies)} ms")
print("=" * 50)
