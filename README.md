# Project AtlasCare

> Agentic AI customer support system built with a deterministic LangGraph workflow and a dual-model LLM strategy (Llama 3.3 70B & Llama 3.1 8B via Groq), designed for observability, deterministic safety, and enterprise-grade architecture.

---

## Overview

AtlasCare is an autonomous customer support agent that processes natural language queries through a **compiled LangGraph StateGraph**. Instead of an open-ended ReAct loop, the system uses a deterministic 8-node graph where the LLM is restricted to structured extraction and response synthesis — all tool dispatch, governance, and workflow planning are handled by Python code.

It demonstrates four end-to-end customer journeys:

| Journey | Description | Key Behavior |
|---------|-------------|--------------|
| **J1** — Simple Tracking | "Where is my order ORD-J1?" | Fast-path (skips LLM), single OMS call, returns status + tracking |
| **J2** — Compound Request | Cancel item + refund + update address | Multi-step plan, guardrail blocks ₹85K refund, CRM escalation |
| **J3** — Escalation | Cancel order + refund ₹42K | Refund blocked pre-execution, CRM case created with trace_id |
| **J4** — Policy Lookup | "What is your return policy?" | Fast-path (skips LLM), single KB call, returns policy articles |

### Key Design Principles

- **Dual-Model Routing**: Optimizes for both accuracy and speed by utilizing two distinct models (configured centrally in `utils/llm_client.py`):
  - **Structured Extraction Node**: Uses the heavy, reasoning-focused model (`Llama-3.3-70b-versatile`) to accurately parse intents and entities.
  - **Response Synthesis Node**: Uses the lightweight, extremely fast model (`Llama-3.1-8b-instant`) solely to format the final customer text, reducing latency significantly.
- **Safety First**: Refund threshold (₹25,000) is a hard-coded guardrail — never an LLM decision
- **Deterministic Governance**: The LLM extracts "what the user wants" and synthesizes "what to say." Python code decides "what to do."
- **Observability**: Every interaction produces a structured trace with `trace_id`, per-node latencies, workflow summary, and full `tool_calls` log
- **Auditability**: CRM cases link back to traces via `trace_id`; tool call logs enable complete interaction replay
- **Resilience**: Tool calls go through retry + timeout + circuit breaker; LLM calls have cached fallbacks
- **Extensibility**: Tools follow a unified `BaseTool` interface with auto-discovery via registry

---

## Setup & Running

### Prerequisites
- Python 3.11+
- A Groq API key ([get one here](https://console.groq.com/keys))

### Installation

```bash
# 1. Create virtual environment
python -m venv venv

# 2. Activate it
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure API key
cp .env.example .env
# Edit .env and set: GROQ_API_KEY=your-actual-key
```

### Start the Server

```bash
uvicorn main:app --reload
```

Server runs at `http://localhost:8000`. API docs at `http://localhost:8000/docs`.

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/query` | Process a customer support query |
| `GET` | `/health` | Health check for monitoring |
| `GET` | `/trace/{trace_id}` | Retrieve full interaction trace |

### Request/Response Contract

**Request** (`POST /query`):
```json
{
  "message": "Where is my order ORD-J1?",
  "session_id": "unique-session-id"
}
```

**Response**:
```json
{
  "response": "Your order ORD-J1 is currently shipped...",
  "trace": {
    "trace_id": "uuid-here",
    "session_id": "unique-session-id",
    "latency_ms": 2500,
    "tool_calls": [...],
    "retry_counts": {},
    "policy_violations": []
  }
}
```

---

## Running the Four Journeys (curl)

### J1 — Simple Tracking

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"message": "Where is my order ORD-J1?", "session_id": "j1-test"}'
```

**Expected**: Single OMS tool call in trace, response contains order status + tracking number.

### J2 — Compound Request (Cancel + Refund + Address Update)

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"message": "Cancel my order ORD-J2 item 1, refund me 85000, and update my address to New Address.", "session_id": "j2-test"}'
```

**Expected**: OMS cancel + CRM escalation case (₹85K > ₹25K limit) + OMS address update. NO payments tool call in trace.

### J3 — Escalation with Audit Trail

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"message": "Cancel order ORD-J3 and refund me 42000.", "session_id": "j3-test"}'
```

**Expected**: OMS cancel + CRM case with `trace_id` linkage. NO payments tool call in trace (blocked by guardrail).

### J4 — Policy Lookup

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"message": "What is your return policy?", "session_id": "j4-test"}'
```

**Expected**: KB `search_policy` call; response contains policy data. Fast-path — no LLM extraction call.

### Retrieve a Trace (Audit Replay)

```bash
curl http://localhost:8000/trace/{trace_id}
```

---

## Running the Demo Script

```bash
python demo.py
```

Runs J1, J2, and J3 sequentially with formatted output including structured traces.

---

## Tests

```bash
pytest tests/ -v
```

Tests cover:
- All 4 journeys (J1, J2, J3, J4) — API contract and expected behavior
- Graph state transitions — node traversal paths for each journey type
- Graph node unit tests — individual node behavior in isolation
- Guardrail edge cases (₹25,000 boundary, ₹25,001, ₹42,000)
- Schema contract validation (trace_id, latency_ms, tool_calls)
- Governance invariants (injection attacks, idempotency)
- Enriched trace metadata (retry_counts, policy_violations)
- Negative tests (empty query, invalid order ID)

---

## Project Structure

```
├── main.py                           # FastAPI app, endpoints, input sanitization
├── demo.py                           # Demo script — runs J1/J2/J3 sequentially
├── requirements.txt                  # Dependencies
├── .env.example                      # Environment configuration template
├── architecture.md                   # System architecture document
├── kpi_framework.md                  # KPI definitions and measurement
├── test_plan.md                      # Testing strategy and scope
│
├── agent/
│   ├── __init__.py                   # Package init, shared _trace_store
│   ├── orchestrator.py               # Thin adapter: AgentState → graph.ainvoke → QueryResponse
│   ├── graph.py                      # LangGraph StateGraph definition (8 nodes, conditional edges)
│   ├── state.py                      # AgentState TypedDict — shared state across all nodes
│   ├── intent.py                     # Intent classification (regex + patterns)
│   ├── planner.py                    # Multi-step plan generation with dependency ordering
│   ├── prompts.py                    # All system prompts centralized (extraction, synthesis)
│   └── nodes/
│       ├── __init__.py               # Node package init
│       ├── regex_router.py           # Node 1: Fast regex-based intent + entity extraction
│       ├── structured_extraction.py  # Node 2: LLM call #1 — strict JSON extraction
│       ├── policy_validation.py      # Node 3: Pre-flight guardrail checks
│       ├── workflow_planner.py       # Node 4: Converts intents → ordered tool plan
│       ├── deterministic_executor.py # Node 5: Executes tool calls via resilience wrapper
│       ├── escalation_handler.py     # Node 6a: Creates CRM case on guardrail block
│       ├── response_generator.py     # Node 6b: LLM call #2 — customer-facing text synthesis
│       └── trace_finalizer.py        # Node 7: Writes enriched trace to store
│
├── tools/
│   ├── __init__.py                   # Package init
│   ├── base.py                       # BaseTool abstract class (ABC)
│   ├── registry.py                   # Auto-discovery tool registry
│   ├── oms.py                        # Order Management System (get_order_status, cancel, address)
│   ├── crm.py                        # CRM tool (get_customer_profile, create_case)
│   ├── kb.py                         # Knowledge Base tool (search_policy)
│   └── payments.py                   # Payments tool (initiate_refund, with threshold guard)
│
├── guardrails/
│   ├── __init__.py                   # Package init
│   ├── refund_limit.py               # Hard-coded ₹25,000 refund check
│   ├── hallucination.py              # Response grounding validation
│   └── escalation.py                 # Escalation detection logic
│
├── models/
│   ├── __init__.py                   # Package init
│   └── schemas.py                    # Pydantic models (QueryRequest, QueryResponse, TraceInfo)
│
├── data/
│   ├── orders.json                   # Mock order data (ORD-J1, ORD-J2, ORD-J3)
│   ├── customers.json                # Mock customer data (CUST-001)
│   ├── knowledge_base.json           # Mock KB articles (return/refund policies)
│   └── payments_config.json          # Payment gateway config
│
├── utils/
│   ├── __init__.py                   # Package init
│   ├── llm_client.py                 # Groq API client (Llama 3.3 70B & Llama 3.1 8B) with retry + cached fallback
│   ├── resilience.py                 # Retry + timeout + circuit breaker for tool execution
│   ├── tracing.py                    # trace_id / session_id generation
│   ├── logger.py                     # Structured JSON logging (structlog)
│   └── pii.py                        # PII masking for logs
│
└── tests/
    ├── __init__.py                   # Package init
    ├── conftest.py                   # Pytest fixtures and shared configuration
    ├── test_j1_tracking.py           # Journey 1 tests
    ├── test_j2_compound.py           # Journey 2 tests
    ├── test_j3_escalation.py         # Journey 3 tests
    ├── test_j4_policy.py             # Journey 4 tests
    ├── test_state_transitions.py     # End-to-end graph state transition tests
    └── test_graph_nodes.py           # Unit tests for individual graph nodes
```
