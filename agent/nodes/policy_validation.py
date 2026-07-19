"""
Policy Validation Node — Pre-Flight Deterministic Governance Engine

This node is the authoritative governance checkpoint. It runs BEFORE any
tool is executed, checking ALL policies against the extracted state.

Critical design principle:
  Policy enforcement is NEVER delegated to the LLM. This node runs
  hard-coded deterministic checks. If escalation is required, it sets
  `escalation_required=True` so the executor never even attempts the
  blocked operation.

Current policies enforced:
  1. Refund auto-approval threshold: ₹25,000 (hard-coded constant)
  2. Explicit escalation request (customer asked for human)

Extension points (add new policies here):
  3. Customer tier restrictions (e.g. Bronze tier cannot cancel after 24h)
  4. Order status eligibility (e.g. cannot cancel delivered orders)
  5. Duplicate refund detection (same order_id + amount in recent history)
"""

import time
from typing import Any, Dict, List

from agent.state import AgentState
from guardrails.refund_limit import REFUND_AUTO_LIMIT
from utils.logger import logger


def _ms_since(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)


async def policy_validation_node(state: AgentState) -> Dict[str, Any]:
    """
    Pre-flight deterministic policy validation.

    Checks all governance policies against the extracted state BEFORE
    any tools are executed. This is the first of two refund-limit checks
    (the second is inside deterministic_executor_node as defense-in-depth).

    Sets escalation_required=True if any policy is violated.
    Sets policy_violations with human-readable violation descriptions.

    The executor node reads escalation_required and SKIPS the blocked
    operation — it is never even attempted.

    Returns:
        Partial AgentState with policy_violations, escalation_required,
        escalation_reason updated.
    """
    t0 = time.perf_counter()
    trace_id = state.get("trace_id", "")

    violations: List[str] = list(state.get("policy_violations", []))
    escalation_required: bool = state.get("escalation_required", False)
    escalation_reason: str = state.get("escalation_reason", "")

    # ── Policy 1: Refund Auto-Approval Threshold ──────────────────────────
    # Hard-coded ₹25,000 limit. Never read from config or LLM.
    # This is the pre-flight check; executor does a second check at execution time.
    refund_amount = state.get("refund_amount")
    if refund_amount is not None and float(refund_amount) > REFUND_AUTO_LIMIT:
        reason = (
            f"Refund amount ₹{refund_amount:,.0f} exceeds auto-approval "
            f"limit of ₹{REFUND_AUTO_LIMIT:,}"
        )
        violations.append(reason)
        if not escalation_required:
            escalation_required = True
            escalation_reason = reason
        logger.warning(
            "Policy violation: refund threshold",
            trace_id=trace_id,
            refund_amount=refund_amount,
            limit=REFUND_AUTO_LIMIT,
        )

    # ── Policy 2: Explicit Customer Escalation Request ────────────────────
    extracted_intents = state.get("extracted_intents", [])
    if "ESCALATION" in extracted_intents and not escalation_required:
        reason = "Customer explicitly requested human agent escalation"
        violations.append(reason)
        escalation_required = True
        escalation_reason = reason
        logger.info(
            "Policy: explicit escalation request",
            trace_id=trace_id,
        )

    latency = _ms_since(t0)
    existing_latencies = dict(state.get("node_latencies", {}))
    existing_latencies["policy_validation"] = latency

    existing_transitions = list(state.get("node_transitions", []))
    existing_transitions.append("policy_validation")

    logger.info(
        "Policy validation completed",
        trace_id=trace_id,
        violations=len(violations),
        escalation_required=escalation_required,
        latency_ms=latency,
    )

    return {
        "policy_violations": violations,
        "escalation_required": escalation_required,
        "escalation_reason": escalation_reason,
        "node_latencies": existing_latencies,
        "node_transitions": existing_transitions,
    }
