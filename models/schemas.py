"""
Pydantic Models — Request/Response Schemas

Defines the API contract for AtlasCare endpoints:
- QueryRequest: Inbound customer query (channel-agnostic)
- QueryResponse: Agent response with full trace
- TraceInfo: Enriched observability trace (backward-compatible)
- ToolCallInfo: Individual tool call audit record
- NodeSpan: Per-graph-node latency record
- WorkflowSummary: High-level workflow execution summary
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    """
    Inbound customer support query — channel-agnostic API contract.

    The `channel` field supports future email/voice adapters that normalize
    their payloads to this schema. Existing callers using only `message` and
    `session_id` are unaffected — `channel` defaults to "chat".
    """
    message: str = Field(..., description="Natural language customer query")
    session_id: str = Field(..., description="Session identifier for conversation tracking")
    channel: str = Field(
        default="chat",
        description="Interaction channel: 'chat' | 'email' | 'voice'",
    )
    customer_id: Optional[str] = Field(
        default=None,
        description="Optional customer ID override (used by channel adapters)",
    )


class ToolCallInfo(BaseModel):
    """Audit record for a single tool call within a trace."""
    tool: str = Field(..., description="Tool name (oms, crm, kb, payments)")
    params: Dict[str, Any] = Field(..., description="Parameters passed to the tool")
    result: str = Field(..., description="Outcome: success, error, or blocked")
    data: Optional[Dict[str, Any]] = Field(default=None, description="Structured result data")
    timestamp: str = Field(..., description="ISO-8601 UTC timestamp of execution")


class NodeSpan(BaseModel):
    """
    Latency record for a single LangGraph node execution.

    Enables per-node performance profiling and identification of bottlenecks
    in the workflow execution path.
    """
    node: str = Field(..., description="Graph node name")
    latency_ms: int = Field(..., description="Node execution latency in milliseconds")
    timestamp: str = Field(..., description="ISO-8601 UTC timestamp when node completed")


class WorkflowSummary(BaseModel):
    """
    High-level summary of the workflow execution.

    Designed for operations dashboards and monitoring. Provides a quick
    view of what happened without requiring full tool_calls inspection.
    """
    intent: str = Field(..., description="Primary classified intent")
    workflow_type: str = Field(
        ...,
        description="Workflow route taken: TRACKING | COMPOUND | ESCALATION | POLICY | GENERAL | MULTI_INTENT",
    )
    steps_planned: int = Field(default=0, description="Total steps in the execution plan")
    steps_completed: int = Field(default=0, description="Steps that completed successfully")
    steps_failed: int = Field(default=0, description="Steps that failed or were blocked")
    steps_skipped: int = Field(default=0, description="Steps skipped due to idempotency or dependency")
    escalation_triggered: bool = Field(
        default=False, description="Whether human escalation was triggered"
    )
    node_path: List[str] = Field(
        default_factory=list,
        description="Ordered list of graph nodes traversed",
    )
    channel: str = Field(default="chat", description="Interaction channel")


class TraceInfo(BaseModel):
    """
    Enriched observability trace for a complete interaction.

    Backward-compatible: all new fields are Optional with defaults.
    Existing `trace_id`, `session_id`, `latency_ms`, and `tool_calls`
    fields are unchanged and will always be present.
    """
    trace_id: str = Field(..., description="Unique trace identifier (UUID)")
    session_id: str = Field(..., description="Session identifier for conversation tracking")
    latency_ms: int = Field(..., description="End-to-end latency in milliseconds")
    tool_calls: List[ToolCallInfo] = Field(
        default_factory=list,
        description="Ordered list of all tool calls made during this interaction",
    )
    # ── New observability fields (optional, backward-compatible) ──────────
    node_spans: List[NodeSpan] = Field(
        default_factory=list,
        description="Per-graph-node latency breakdown",
    )
    workflow_summary: Optional[WorkflowSummary] = Field(
        default=None,
        description="High-level workflow execution summary for dashboards",
    )
    retry_counts: Dict[str, int] = Field(
        default_factory=dict,
        description="Per-tool retry counts (tool_name → retry_count)",
    )
    policy_violations: List[str] = Field(
        default_factory=list,
        description="Policy violations detected during this interaction",
    )


class QueryResponse(BaseModel):
    """Agent response with observability trace."""
    response: str = Field(..., description="Natural language response to the customer")
    trace: TraceInfo = Field(..., description="Full interaction trace for audit/replay")
