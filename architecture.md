# AtlasCare Architecture

# Overview

AtlasCare uses a **deterministic LangGraph workflow** backed by Llama 3.3 70B Versatile via the Groq API (OpenAI-compatible endpoint). Instead of an unpredictable ReAct loop, the system routes customer queries through a compiled **StateGraph** with explicit nodes, conditional edges, and bounded execution — ensuring full auditability, governance, and predictability.

The LLM is constrained to exactly **two roles**:
1. **Structured extraction** — parse user intent and entities into strict JSON
2. **Response synthesis** — convert tool results into customer-facing text

All tool dispatch, policy enforcement, and workflow planning are handled by deterministic Python code.

## System Diagram

```
┌─────────────────────────────────────────────────────┐
│                    FastAPI Server                     │
│  POST /query     GET /health     GET /trace/{id}     │
├─────────────────────────────────────────────────────┤
│          Agent Orchestrator (thin adapter)            │
│  Initializes AgentState → invokes LangGraph graph    │
│  → converts final state to QueryResponse             │
├─────────────────────────────────────────────────────┤
│            LangGraph StateGraph (8 nodes)             │
│                                                      │
│  regex_router ──┬──> structured_extraction (LLM #1)  │
│                 └──> policy_validation (fast-path)    │
│                           │                          │
│                    workflow_planner                   │
│                           │                          │
│                 deterministic_executor                │
│                    ┌──────┴──────┐                    │
│             escalation_handler   │                   │
│                    └──────┬──────┘                    │
│                 response_generator (LLM #2)          │
│                           │                          │
│                    trace_finalizer → END              │
├─────────────────────────────────────────────────────┤
│               Guardrails Layer                        │
│  - Refund threshold (hard-coded ₹25,000)             │
│  - Hallucination prevention (grounding check)        │
│  - PII masking in structured logs                    │
│  - Input sanitization (SQL/XSS patterns)             │
├─────────────────────────────────────────────────────┤
│           Tool Registry (auto-discovery)              │
│  ┌─────────┐ ┌─────────┐ ┌──────┐ ┌──────────────┐ │
│  │   OMS   │ │   CRM   │ │  KB  │ │   Payments   │ │
│  │  Tool   │ │  Tool   │ │ Tool │ │    Tool      │ │
│  └─────────┘ └─────────┘ └──────┘ └──────────────┘ │
├─────────────────────────────────────────────────────┤
│           Resilience Layer (per-tool)                 │
│  - Retry with exponential backoff + jitter           │
│  - Per-call timeout (5s)                             │
│  - Circuit breaker (open after 5 consecutive fails)  │
├─────────────────────────────────────────────────────┤
│              Mock Data Layer (JSON files)             │
└─────────────────────────────────────────────────────┘
```

## Components

| Component | File(s) | Responsibility |
|-----------|---------|----------------|
| **API Layer** | `main.py` | FastAPI endpoints, input sanitization, error handling |
| **Orchestrator** | `agent/orchestrator.py` | Thin adapter: initializes AgentState, invokes the LangGraph graph, converts result to QueryResponse |
| **State** | `agent/state.py` | AgentState TypedDict — the shared state passed between all graph nodes |
| **Graph Builder** | `agent/graph.py` | Defines the 8-node StateGraph with conditional edges, compiles to singleton |
| **Node: Regex Router** | `agent/nodes/regex_router.py` | Fast regex-based intent + entity extraction (no LLM call) |
| **Node: Structured Extraction** | `agent/nodes/structured_extraction.py` | LLM call #1 — strict JSON intent/entity extraction for complex queries |
| **Node: Policy Validation** | `agent/nodes/policy_validation.py` | Pre-flight guardrail checks (refund limit) before planning |
| **Node: Workflow Planner** | `agent/nodes/workflow_planner.py` | Converts intents + entities into an ordered tool execution plan |
| **Node: Deterministic Executor** | `agent/nodes/deterministic_executor.py` | Executes planned tool calls sequentially via resilience wrapper |
| **Node: Escalation Handler** | `agent/nodes/escalation_handler.py` | Creates CRM case when guardrail blocks a step mid-execution |
| **Node: Response Generator** | `agent/nodes/response_generator.py` | LLM call #2 — synthesizes customer-facing text from tool results |
| **Node: Trace Finalizer** | `agent/nodes/trace_finalizer.py` | Writes enriched trace (node_spans, workflow_summary) to trace store |
| **Intent Classifier** | `agent/intent.py` | Regex-based classification: TRACKING, COMPOUND, ESCALATION, POLICY, GENERAL |
| **Planner** | `agent/planner.py` | Decomposes compound requests into ordered steps with dependency logic |
| **Prompts** | `agent/prompts.py` | All system prompts centralized (extraction, synthesis, legacy) |
| **Tool Registry** | `tools/registry.py` | Auto-discovery of tools, unified schema generation |
| **Guardrails** | `guardrails/*.py` | Refund limit, hallucination check, escalation detection |
| **Resilience** | `utils/resilience.py` | Retry + timeout + circuit breaker wrapper for tool execution |
| **LLM Client** | `utils/llm_client.py` | Groq API client (Llama 3.3 70B) with retry + exponential backoff + cached fallback |
| **Tracing** | `utils/tracing.py` | UUID trace_id generation, latency measurement |
| **Logger** | `utils/logger.py` | Structured JSON logging with PII masking |

## Graph Node Flow

```
START → regex_router
           │
           ├─ (fast-path: TRACKING/POLICY) ──→ policy_validation
           └─ (complex: COMPOUND/etc.)    ──→ structured_extraction → policy_validation
                                                        │
                                                 workflow_planner
                                                        │
                                              deterministic_executor
                                                   │          │
                                    (escalation) ──→ escalation_handler
                                                   │          │
                                                   └────┬─────┘
                                                        │
                                              response_generator
                                                        │
                                                 trace_finalizer → END
```

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| LangGraph StateGraph over ReAct loop | Explicit state transitions, bounded execution, full auditability. No hidden LLM state — every decision point is a Python function. |
| Hard-coded ₹25,000 refund limit | Business-critical threshold must NOT depend on LLM . Defense-in-depth: checked in BOTH policy_validation_node (pre-flight) and deterministic_executor_node (mid-execution). |
| Sequential tool execution | Ensures causal dependencies are respected (cancel must succeed before refund). Partial failures are reported, not silently skipped. |
| LLM restricted to extraction + synthesis | The LLM cannot trigger tool calls directly. It extracts "what the user wants" and later generates "what to say." Python code handles "what to do." |
| Fast-path routing | Simple TRACKING and POLICY queries skip the LLM extraction node entirely, saving ~500-800ms per request. |
| Regex-based intent classification | Fast and deterministic for common patterns. No LLM latency for simple queries. |
| OpenAI-compatible endpoint (Groq) | Groq's OpenAI-compatible API allows using standard chat/completions without vendor lock-in. Swapping models requires changing one line. |
| Cached fallback responses | When Groq API is unavailable (rate limits, errors), deterministic cached responses keep the system running end-to-end. |
| Resilience wrapper for tools | Every tool call goes through retry + timeout + circuit breaker to handle transient failures gracefully. |

## Security

- **Refund Guardrail**: Hard-coded ₹25,000 limit at code level, NOT in prompts 
- **Input Sanitization**: SQL injection and XSS patterns stripped from user input before processing
- **PII Masking**: Email, phone, and Aadhaar numbers masked in all structured log output
- **API Key Security**: Groq API key read from environment variable (`GROQ_API_KEY`), never committed to code

## Observability

- **Structured Logging**: All events emitted as JSON via structlog with ISO timestamps
- **Trace Replay**: Every interaction stored with full tool call history, node spans, and workflow summary — retrievable via `GET /trace/{id}`
- **Latency Tracking**: End-to-end + per-node latency measured with `time.perf_counter()` for precision
- **Hallucination Detection**: Post-generation check validates LLM responses are grounded in tool data
- **Node Transitions**: Every graph node traversal recorded in state for debugging

## Error Handling

- **LLM Retry Logic**: 3 retries with exponential backoff + jitter for rate limits and server errors
- **Graceful Degradation**: Cached fallback responses when Groq API is unavailable; deterministic response builder when LLM synthesis fails
- **Tool Resilience**: Per-tool retry (3 attempts) + timeout (5s) + circuit breaker (opens after 5 consecutive failures)
- **Tool Failure Reporting**: Partial failures in multi-step plans are reported to the user, not silently skipped
- **Global Exception Handler**: Unhandled errors return structured error responses, never raw stack traces

## Scaling Considerations

- **Stateless API**: Horizontal scaling behind a load balancer (no in-process session state beyond traces)
- **Session Externalization**: Redis-backed session/trace store (not implemented in MVP — swap `_trace_store` dict)
- **Circuit Breaker Externalization**: Replace in-process `_CircuitBreakerState` with Redis INCR/EXPIRE for multi-worker consistency
- **Checkpointer**: LangGraph compiled graph supports `AsyncPostgresSaver` or `RedisSaver` for persistent checkpointing
- **Tool Idempotency**: Tool calls are idempotent where possible (e.g., status queries, address updates)
- **Rate Limit Handling**: Exponential backoff prevents cascading failures under load
