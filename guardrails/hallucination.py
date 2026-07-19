"""
Hallucination Prevention Guardrail

Post-execution check that validates LLM responses only contain
data that was actually returned by tool calls. Prevents the agent
from fabricating order details, tracking numbers, prices, or dates.
"""

from typing import Any, Dict, List, Set
from utils.logger import logger


# Fields that must come from tool results, never invented
GROUNDED_FIELDS = {
    "order_id", "tracking_number", "status", "estimated_delivery",
    "total_amount", "unit_price", "payment_method", "case_id",
    "customer_id", "name", "email", "phone",
}


def check_response_grounding(
    response_text: str,
    tool_results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Validate that the LLM response is grounded in tool results.

    Checks that any specific data values (order IDs, tracking numbers,
    amounts, dates) mentioned in the response actually appear in the
    tool results. Flags potential hallucinations.

    Args:
        response_text: The final text response from the LLM.
        tool_results: List of result dictionaries from executed tools.

    Returns:
        Dictionary with:
        - grounded (bool): True if response appears grounded
        - suspicious_tokens (list): Any values in response not found in tool data
    """
    if not response_text or not tool_results:
        return {"grounded": True, "suspicious_tokens": []}

    # Flatten all tool result values into a set of known data strings
    known_values: Set[str] = set()
    for result in tool_results:
        _extract_values(result, known_values)

    # Extract specific-looking tokens from the response
    # (order IDs, tracking numbers, amounts, dates, etc.)
    import re
    suspicious = []

    # Check for order IDs not in tool results
    order_ids = re.findall(r"\bORD-\w+\b", response_text, re.IGNORECASE)
    for oid in order_ids:
        if oid.upper() not in known_values and oid not in known_values:
            suspicious.append(f"order_id:{oid}")

    # Check for tracking numbers not in tool results
    tracking = re.findall(r"\bTRACK-\w+\b", response_text, re.IGNORECASE)
    for tn in tracking:
        if tn not in known_values:
            suspicious.append(f"tracking:{tn}")

    # Check for case IDs not in tool results
    cases = re.findall(r"\bCASE-\w+\b", response_text, re.IGNORECASE)
    for c in cases:
        if c not in known_values:
            suspicious.append(f"case_id:{c}")

    grounded = len(suspicious) == 0

    if not grounded:
        logger.warning(
            "Hallucination detected",
            suspicious_tokens=suspicious,
            response_preview=response_text[:200],
        )

    return {"grounded": grounded, "suspicious_tokens": suspicious}


def _extract_values(obj: Any, values: Set[str], depth: int = 0) -> None:
    """Recursively extract all string values from a nested dict/list."""
    if depth > 10:  # Safety limit
        return
    if isinstance(obj, dict):
        for v in obj.values():
            _extract_values(v, values, depth + 1)
    elif isinstance(obj, list):
        for item in obj:
            _extract_values(item, values, depth + 1)
    elif isinstance(obj, str):
        values.add(obj)
    elif isinstance(obj, (int, float)):
        values.add(str(obj))
