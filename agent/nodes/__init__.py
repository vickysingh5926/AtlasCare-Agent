"""
LangGraph Nodes Package — AtlasCare Workflow Orchestration

Each module in this package implements a single LangGraph node function.
Nodes return partial AgentState dicts; LangGraph merges them automatically.

Node execution order:
  regex_router → structured_extraction → policy_validation
  → workflow_planner → deterministic_executor
  → escalation_handler (conditional) → response_generator → trace_finalizer

All nodes are async. All governance decisions are deterministic.
LLMs are used ONLY in: structured_extraction, response_generator.
"""
