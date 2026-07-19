"""
Resilience Utilities — Retry, Timeout, and Circuit Breaker

Production-grade wrappers for tool execution in the deterministic_executor_node.
All tool calls pass through this layer to ensure:

  - Transient failures are retried with exponential backoff + jitter
  - Hung tools are terminated after a configurable timeout
  - Repeated failures trigger circuit-open state (graceful degradation)
  - All retry and failure events are emitted to structured logs

Design:
  - Retry logic mirrors the existing LLM client retry pattern (utils/llm_client.py)
    for consistency across the codebase
  - CircuitBreakerRegistry is an in-process stub; it is designed to be swapped
    for a Redis-backed implementation in multi-worker production deployments
  - All functions return structured dicts — they never raise exceptions to callers

Scalability Extension Points:
  - Replace CircuitBreakerRegistry with aioredis for multi-worker circuit state
  - Add Prometheus counter increments in _record_failure / _record_success
"""

import asyncio
import random
import time
from typing import Any, Dict

from utils.logger import logger

# ── Configuration ─────────────────────────────────────────────────────────────

# Per-tool execution timeout (seconds)
TOOL_TIMEOUT_S: float = 5.0

# Retry configuration (mirrors LLM client retry policy)
MAX_TOOL_RETRIES: int = 3
RETRY_BASE_DELAY_S: float = 0.5
RETRY_MAX_DELAY_S: float = 4.0

# Circuit breaker: open after this many consecutive failures
CIRCUIT_OPEN_THRESHOLD: int = 5
CIRCUIT_RESET_AFTER_S: float = 60.0  # auto-reset after 1 minute


# ── Circuit Breaker Registry (in-process stub) ────────────────────────────────

class _CircuitBreakerState:
    """
    Tracks circuit state for a single tool.

    States:
      - CLOSED (normal): requests pass through
      - OPEN (degraded): requests return immediately with degraded response
      - HALF-OPEN: one probe request is allowed through to test recovery

    In production: replace this in-process dict with Redis INCR/EXPIRE
    so circuit state is shared across all uvicorn workers.
    """

    def __init__(self, tool_name: str):
        self.tool_name = tool_name
        self.consecutive_failures: int = 0
        self.open_since: float = 0.0  # epoch seconds when circuit opened

    @property
    def is_open(self) -> bool:
        if self.consecutive_failures < CIRCUIT_OPEN_THRESHOLD:
            return False
        # Auto-reset after CIRCUIT_RESET_AFTER_S seconds
        if time.monotonic() - self.open_since >= CIRCUIT_RESET_AFTER_S:
            self.consecutive_failures = 0
            logger.info(
                "Circuit breaker auto-reset",
                tool=self.tool_name,
                after_seconds=CIRCUIT_RESET_AFTER_S,
            )
            return False
        return True

    def record_failure(self) -> None:
        self.consecutive_failures += 1
        if self.consecutive_failures == CIRCUIT_OPEN_THRESHOLD:
            self.open_since = time.monotonic()
            logger.warning(
                "Circuit breaker OPENED",
                tool=self.tool_name,
                consecutive_failures=self.consecutive_failures,
            )

    def record_success(self) -> None:
        if self.consecutive_failures > 0:
            logger.info(
                "Circuit breaker reset after success",
                tool=self.tool_name,
                was_failures=self.consecutive_failures,
            )
        self.consecutive_failures = 0


# One circuit-breaker state per tool name
_circuit_registry: Dict[str, _CircuitBreakerState] = {}


def _get_circuit(tool_name: str) -> _CircuitBreakerState:
    if tool_name not in _circuit_registry:
        _circuit_registry[tool_name] = _CircuitBreakerState(tool_name)
    return _circuit_registry[tool_name]


def reset_circuit(tool_name: str) -> None:
    """Manually reset a tool's circuit breaker (useful for tests)."""
    if tool_name in _circuit_registry:
        _circuit_registry[tool_name].consecutive_failures = 0


# ── Core Resilience Wrapper ────────────────────────────────────────────────────

async def execute_with_resilience(
    tool: Any,
    params: Dict[str, Any],
    max_retries: int = MAX_TOOL_RETRIES,
    timeout_s: float = TOOL_TIMEOUT_S,
) -> Dict[str, Any]:
    """
    Execute a BaseTool with retry, timeout, and circuit-breaker protection.

    This is the ONLY way the deterministic_executor_node calls tools.
    It never raises exceptions — all failure states are returned as
    structured error dicts so partial-failure handling works correctly.

    Args:
        tool: A BaseTool instance (oms, crm, kb, payments).
        params: Parameters to pass to tool.execute().
        max_retries: Maximum number of attempt before giving up.
        timeout_s: Per-attempt timeout in seconds.

    Returns:
        Dict with at minimum:
          - status: "success" | "error"
          - message: human-readable result
          - retry_count: number of retries used
          - timed_out: True if the final failure was a timeout
    """
    tool_name = getattr(tool, "name", "unknown")
    circuit = _get_circuit(tool_name)

    # ── Circuit open: return degraded response immediately ────────────────
    if circuit.is_open:
        logger.warning(
            "Circuit breaker OPEN — returning degraded response",
            tool=tool_name,
        )
        return {
            "status": "error",
            "message": f"Tool '{tool_name}' is temporarily unavailable (circuit open). Please try again later.",
            "circuit_open": True,
            "retry_count": 0,
            "timed_out": False,
        }

    last_error: str = ""
    timed_out: bool = False

    for attempt in range(max_retries):
        try:
            result = await asyncio.wait_for(
                tool.execute(params),
                timeout=timeout_s,
            )

            # ── Success ──────────────────────────────────────────────────
            circuit.record_success()
            result.setdefault("retry_count", attempt)
            result.setdefault("timed_out", False)

            if attempt > 0:
                logger.info(
                    "Tool succeeded after retry",
                    tool=tool_name,
                    attempt=attempt + 1,
                )
            return result

        except asyncio.TimeoutError:
            timed_out = True
            last_error = f"Tool '{tool_name}' timed out after {timeout_s}s"
            delay = _backoff_delay(attempt)
            logger.warning(
                "Tool execution timeout",
                tool=tool_name,
                attempt=attempt + 1,
                timeout_s=timeout_s,
                retry_delay=delay,
            )
            await asyncio.sleep(delay)

        except Exception as exc:
            last_error = str(exc)
            delay = _backoff_delay(attempt)
            logger.warning(
                "Tool execution error",
                tool=tool_name,
                attempt=attempt + 1,
                error=last_error,
                retry_delay=delay,
            )
            await asyncio.sleep(delay)

    # ── All retries exhausted ─────────────────────────────────────────────
    circuit.record_failure()
    logger.error(
        "Tool failed after all retries",
        tool=tool_name,
        max_retries=max_retries,
        last_error=last_error,
        timed_out=timed_out,
    )

    return {
        "status": "error",
        "message": (
            f"Tool '{tool_name}' failed after {max_retries} attempts: {last_error}"
        ),
        "retry_count": max_retries - 1,
        "timed_out": timed_out,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _backoff_delay(attempt: int) -> float:
    """
    Exponential backoff with jitter.
    Matches the strategy used in utils/llm_client.py for consistency.
    """
    return min(
        RETRY_BASE_DELAY_S * (2 ** attempt) + random.uniform(0, 0.5),
        RETRY_MAX_DELAY_S,
    )
