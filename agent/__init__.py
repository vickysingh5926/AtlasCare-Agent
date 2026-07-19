# Agent module — orchestrator, intent classification, planner, prompts
# Shared in-memory trace store. Written by trace_finalizer_node, read by get_trace().
# In production: replace with Redis client for cross-worker consistency.
from typing import Any, Dict
_trace_store: Dict[str, Any] = {}

from .orchestrator import handle_query, get_trace  # noqa: E402 (import after store init)

__all__ = ["handle_query", "get_trace", "_trace_store"]
