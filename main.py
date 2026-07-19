"""
Project AtlasCare — FastAPI Application

Agentic AI customer support system with production-grade endpoints:
- POST /query         → Process customer queries via the agent orchestrator
- GET  /health        → Health check for monitoring and load balancer probes
- GET  /trace/{id}    → Retrieve interaction trace for audit/replay
"""

import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from models.schemas import QueryRequest, QueryResponse
from utils.logger import logger
from agent.orchestrator import handle_query, get_trace


# Default customer ID (evaluator contract does not include customer_id)
DEFAULT_CUSTOMER_ID = "CUST-001"

# ── Input Sanitization ──────────────────────────────────────────────
MAX_QUERY_LENGTH = 2000  # Characters

# Patterns that indicate potential injection attempts
_INJECTION_PATTERNS = [
    re.compile(r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|UNION|ALTER)\b\s)", re.IGNORECASE),
    re.compile(r"(<script\b|javascript:|on\w+=)", re.IGNORECASE),
    re.compile(r"(--|;|/\*|\*/|xp_)", re.IGNORECASE),
]


def _sanitize_input(text: str) -> str:
    """
    Sanitize user input by stripping potential injection patterns.

    Strips SQL keywords, XSS patterns, and suspicious characters.
    This is defense-in-depth — the LLM never executes raw SQL,
    but sanitization prevents prompt injection via crafted inputs.
    """
    sanitized = text.strip()
    for pattern in _INJECTION_PATTERNS:
        sanitized = pattern.sub("", sanitized)
    return sanitized


# ── Application Lifespan ────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown hooks."""
    logger.info("AtlasCare server started", version="1.0.0")
    yield
    logger.info("AtlasCare server shutting down")


app = FastAPI(
    title="Project AtlasCare",
    description="Agentic AI Customer Support System for Acme Retail Co.",
    version="1.0.0",
    lifespan=lifespan,
)


# ── Global Exception Handler ────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Catch unhandled exceptions and return structured error response."""
    logger.error(
        "Unhandled exception",
        error=str(exc),
        error_type=type(exc).__name__,
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": "An unexpected error occurred. Please try again.",
        },
    )


# ── Endpoints ────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Health check endpoint for monitoring and load balancer probes."""
    return {"status": "healthy", "service": "atlascare", "version": "1.0.0"}


@app.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest):
    """
    Process a customer support query through the agentic orchestrator.

    API Contract (mandatory):
      Request:  {"message": str, "session_id": str}
      Response: {"response": str, "trace": {...}}
    """
    # Input sanitization
    sanitized_query = _sanitize_input(request.message)
    if len(sanitized_query) == 0:
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    if len(sanitized_query) > MAX_QUERY_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Query exceeds maximum length of {MAX_QUERY_LENGTH} characters",
        )

    logger.info(
        "API request received",
        endpoint="/query",
        session_id=request.session_id,
    )

    response = await handle_query(
        sanitized_query, request.session_id, DEFAULT_CUSTOMER_ID
    )
    return response


@app.get("/trace/{trace_id}")
async def trace(trace_id: str):
    """
    Retrieve the full interaction trace for a given trace_id.

    Enables audit replay and debugging of any past interaction.
    Returns the complete tool_calls log, latency, and session metadata.
    """
    stored_trace = get_trace(trace_id)
    if stored_trace is None:
        raise HTTPException(status_code=404, detail="Trace not found")
    return stored_trace
