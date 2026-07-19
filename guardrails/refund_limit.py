"""
Refund Threshold Guardrail — Hard-Coded Safety Check

CRITICAL DESIGN DECISION:
The ₹25,000 refund auto-approval limit is hard-coded as a Python constant.
It is NOT read from environment variables, config files, or databases.

Rationale:
  - Business-critical thresholds must not depend on LLM decisions
  - Even if the LLM hallucinates and tries to call the payments tool,
    this guardrail blocks it at the code level
  - Defense-in-depth: we don't rely on the prompt alone
  - Changing this limit requires a code change + review + deploy cycle

This guard runs BEFORE tool execution in the orchestrator's ReAct loop.
"""

# ──────────────────────────────────────────────────────────────────────
# HARD-CODED CONSTANT — Do NOT read from env, config file, or database.
# Changing this value requires a code change, code review, and redeploy.
# ──────────────────────────────────────────────────────────────────────
REFUND_AUTO_LIMIT = 25_000  # INR


def check_refund_threshold(tool_name: str, params: dict) -> dict:
    """
    Pre-execution guardrail: block refunds exceeding the auto-approval limit.

    This check runs BEFORE the payments tool executes. Even if the LLM
    requests a refund above ₹25,000, this code-level guard prevents it.

    Args:
        tool_name: Name of the tool being called.
        params: Parameters for the tool call.

    Returns:
        dict with:
        - blocked (bool): True if the call should be blocked
        - reason (str): Human-readable explanation (only if blocked)
        - action (str): Recommended follow-up action (only if blocked)
    """
    if tool_name == "payments" and params.get("operation") == "initiate_refund":
        amount = params.get("amount", 0)
        if float(amount) > REFUND_AUTO_LIMIT:
            return {
                "blocked": True,
                "reason": (
                    f"Refund amount ₹{amount:,} exceeds auto-approval "
                    f"limit of ₹{REFUND_AUTO_LIMIT:,}"
                ),
                "action": "escalate_to_human",
            }
    return {"blocked": False}
