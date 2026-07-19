# Test Plan

## Overview

This test plan covers functional, safety, governance, and contract validation for the AtlasCare agent system. Tests are designed to verify the four core customer journeys, the LangGraph state transitions, individual node behavior, and the safety guardrails that protect business-critical operations

---

## In Scope (This Submission)

### Journey Tests

| Test | Journey | Input | Expected Outcome |
|------|---------|-------|-----------------:|
| `test_j1_tracking` | J1 — Tracking | "Where is my order ORD-J1?" | Exactly 1 OMS `get_order_status` call; response contains order data |
| `test_j2_compound` | J2 — Compound | "Cancel my order ORD-J2 item 1, refund me 85000, and update my address to New Address." | OMS cancel + CRM case (₹85K > ₹25K) + OMS address update; NO payments call |
| `test_j3_escalation` | J3 — Escalation | "Cancel order ORD-J3 and refund me 42000." | OMS cancel + CRM case with trace_id; NO payments call in trace |
| `test_j4_policy` | J4 — Policy | "What is your return policy?" | KB `search_policy` call; response contains policy data |

### Graph State Transition Tests

| Test Class | Coverage |
|------------|----------|
| `TestAPIContract` | Response schema validation: `response`, `trace`, `trace_id`, `session_id`, `latency_ms`, `tool_calls` |
| `TestJ1TrackingFastPath` | Verifies fast-path routing (skips structured_extraction), OMS tool call present |
| `TestJ2Compound` | Multi-step execution, payments blocked, CRM case created |
| `TestJ3Escalation` | Guardrail block, CRM case with trace_id, response mentions escalation |
| `TestJ4Policy` | KB tool called, no OMS/payments calls |
| `TestGovernanceInvariants` | ₹25,001 blocked, ₹25,000 not blocked, non-payments never blocked, injection safe, idempotency |
| `TestEnrichedTrace` | retry_counts present, policy_violations present, escalation trace has violations |

### Graph Node Unit Tests

| Test Class | Coverage |
|------------|----------|
| `TestRegexRouterNode` | Tracking/compound/escalation/policy/general intent classification |
| `TestPolicyValidationNode` | Refund limit enforcement, non-refund passthrough |
| `TestWorkflowPlannerNode` | Plan generation for tracking, compound, escalation, policy intents |
| `TestDeterministicExecutorNode` | Tool dispatch, guardrail blocking mid-execution, resilience wrapper |
| `TestEscalationHandlerNode` | CRM case creation with trace_id linkage |
| `TestTraceFinalizerNode` | Trace written to store with node_spans and workflow_summary |

### Guardrail Tests

| Test | Input | Expected |
|------|-------|----------|
| `test_25000_not_blocked` | ₹25,000 | NOT blocked (boundary: limit is "above 25,000") |
| `test_25001_blocked` | ₹25,001 | BLOCKED |
| `test_non_payments_tool_never_blocked` | OMS with ₹1,000,000 | NOT blocked (guardrail only applies to payments tool) |

### Contract Tests

| Assertion | Verified In |
|-----------|-------------|
| Response has `response` (string) and `trace` (object) | All journey tests + TestAPIContract |
| `trace.trace_id` is a valid UUID string | All journey tests |
| `trace.session_id` is present | All journey tests |
| `trace.latency_ms` is a positive integer | All journey tests |
| `trace.tool_calls` is a list of structured records | All journey tests |
| Each tool call has `tool`, `params`, `result`, `timestamp` | All journey tests |
| `trace.retry_counts` is a dict | TestEnrichedTrace |
| `trace.policy_violations` is a list | TestEnrichedTrace |

### Negative Tests

| Test | Input | Expected |
|------|-------|----------|
| `test_empty_query_rejected` | `"   "` (whitespace) | 400 Bad Request |
| `test_injection_attempt_rejected_or_safe` | SQL injection string | 200 or 400, no crash |
| `test_health_endpoint` | `GET /health` | 200 with `{"status": "healthy"}` |
| `test_duplicate_session_idempotent` | Same query sent twice | Both return 200 with different trace_ids |

---

## Out of Scope (Pre-Production Additions)

| Category | Description | Tool |
|----------|-------------|------|
| **Load Testing** | 1000 concurrent sessions, sustained throughput | k6 / locust |
| **LLM Adversarial Testing** | Prompt injection, jailbreak attempts, role-play attacks | Custom red-team scripts |
| **Chaos Testing** | Tool failures mid-sequence, API timeouts, malformed responses | Fault injection framework |
| **Multi-Turn Coherence** | Conversation state across multiple query turns | Custom session replay |
| **PII Leakage Scanning** | Automated scan of all log output for unmasked PII | Regex + DLP tools |
| **Regression Testing** | Automated suite against new LLM model versions | CI/CD pipeline |
| **Circuit Breaker Testing** | Verify circuit breaker opens/resets correctly under sustained tool failure | Custom fault injection |

---

## How to Run

```bash
# Run all tests with verbose output
pytest tests/ -v

# Run a specific journey test
pytest tests/test_j1_tracking.py -v

# Run graph state transition tests
pytest tests/test_state_transitions.py -v

# Run graph node unit tests
pytest tests/test_graph_nodes.py -v

# Run with coverage report
pytest tests/ -v --cov=. --cov-report=term-missing
```

---

## Test Architecture

Tests use the **FastAPI TestClient** for synchronous HTTP-level testing. This validates the full stack from HTTP request through to agent response, including:
- Input sanitization in `main.py`
- Intent classification in `agent/intent.py` and `agent/nodes/regex_router.py`
- LangGraph state transitions in `agent/graph.py`
- Structured extraction via LLM in `agent/nodes/structured_extraction.py`
- Policy validation in `agent/nodes/policy_validation.py`
- Workflow planning in `agent/nodes/workflow_planner.py`
- Deterministic tool execution in `agent/nodes/deterministic_executor.py`
- Guardrail checks in `guardrails/*.py`
- Tool execution via resilience wrapper in `utils/resilience.py`
- Tool calls in `tools/*.py`
- Response synthesis via LLM in `agent/nodes/response_generator.py`
- Trace finalization in `agent/nodes/trace_finalizer.py`
- Response schema validation via Pydantic models in `models/schemas.py`
