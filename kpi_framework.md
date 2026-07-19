# KPI Framework

## Business KPIs

| KPI | Definition | Measurement | Target |
|-----|-----------|-------------|--------|
| **Containment Rate** | % of queries resolved without  escalation | `1 - (escalated_queries / total_queries)` | > 80% |
| **First Contact Resolution** | % of queries resolved in a single session | Queries with no follow-up within 24h | > 85% |
| **Average Handle Time** | Median end-to-end latency per journey type | `trace.latency_ms` aggregated by intent | J1 < 3s, J2 < 8s, J3 < 5s |
| **CSAT Proxy** | User satisfaction indicator | Sentiment analysis on follow-up messages; absence of escalation request after resolution | > 4.0/5.0 |

## Quality KPIs

| KPI | Definition | Measurement | Target |
|-----|-----------|-------------|--------
| **Tool Call Accuracy** | % of tool calls with correct parameters | Compare `tool_calls[].params` against expected values for known test queries | > 95% |
| **Hallucination Rate** | % of responses containing data not returned by tools | `check_response_grounding()` output: `grounded == False` count / total | < 2% |
| **Plan Completion Rate** | % of multi-step plans fully executed (J2) | All planned steps in `tool_calls` with `result == "success"` | > 90% |
| **Response Relevance** | % of responses that directly address the customer's query | Manual review sample + automated keyword matching | > 95% |

## Safety KPIs

| KPI | Definition | Measurement | Target |
|-----|-----------|-------------|--------|
| **Guardrail Trigger Rate** | How often the refund threshold blocks a call | Count of `guardrail_result.blocked == True` events (in policy_validation_node and deterministic_executor_node) | Monitoring only |
| **False Escalation Rate** | Queries escalated that could have been auto-resolved | Manual review of escalated cases with amount ≤ ₹25,000 | < 1% |
| **Threshold Bypass Attempts** | Any refund > ₹25K that reached the Payments tool | Audit `tool_calls` for payments calls with amount > 25000 and result != "blocked" | **Must be 0** |
| **PII Leakage Rate** | Occurrences of unmasked PII in log output | Automated scan of structured logs for email/phone patterns | **Must be 0** |

## Operational KPIs

| KPI | Definition | Measurement | Target |
|-----|-----------|-------------|--------|
| **P50/P95/P99 Latency** | Latency percentiles per endpoint and journey | Histogram of `trace.latency_ms` values | P50 < 2s, P95 < 5s, P99 < 10s |
| **LLM API Error Rate** | Groq API timeout/failure rate | Count of retry events and fallback activations in logs | < 5% |
| **Tool Failure Rate** | Per tool, per error type | Count of `tool_calls[].result == "error"` grouped by tool name | < 2% |
| **Node Traversal Distribution** | Which graph nodes are traversed per query type | Distribution of `node_transitions` paths across queries | Fast-path (2 LLM-skips) for >50% of queries |
| **Circuit Breaker Events** | How often tool circuit breakers open | Count of circuit-open events in structured logs per tool | Monitoring only |
| **Uptime** | Service availability | Health check probe (`GET /health`) success rate | > 99.9% |

## Alerting Recommendations (Pre-Production)

| Alert | Condition | Action |
|-------|-----------|--------|
| Threshold bypass | Any payments tool call with amount > ₹25,000 and result == "success" | **P0** — Immediate investigation |
| High latency | P95 > 10 seconds sustained for 5 minutes | Investigate Groq API performance or tool timeouts |
| Elevated error rate | Tool failure rate > 10% over 15 minutes | Check mock data integrity, tool connectivity |
| Circuit breaker open | Any tool circuit breaker opens | Check tool health, consider manual reset |
| Hallucination spike | Grounding check failure rate > 5% | Review system prompt, update tool descriptions |
| LLM fallback activation | Cached fallback responses > 10% of requests | Investigate Groq API availability or rate limits |
