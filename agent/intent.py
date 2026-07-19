"""
Intent Classification Module

Classifies user queries into intent categories to route them
through the appropriate processing pipeline. Uses keyword
matching for common patterns with LLM fallback for ambiguous cases.
"""

import re
from enum import Enum
from typing import Dict, Optional
from utils.logger import logger


class Intent(str, Enum):
    TRACKING = "TRACKING"
    COMPOUND = "COMPOUND"
    ESCALATION = "ESCALATION"
    POLICY = "POLICY"
    GENERAL = "GENERAL"


# Keyword patterns for fast classification (no LLM call needed)
INTENT_PATTERNS: Dict[Intent, list] = {
    Intent.TRACKING: [
        r"\bwhere\b.*\border\b",
        r"\btrack\b",
        r"\bstatus\b.*\border\b",
        r"\border\b.*\bstatus\b",
        r"\bdelivery\b.*\bstatus\b",
        r"\bdelivery\b.*\bwhen\b",
        r"\bwhen\b.*\bdeliver",
        r"\bshipping\b.*\bstatus\b",
    ],
    Intent.COMPOUND: [
        r"\b(cancel|refund|update|change).*\b(and|also|then)\b",
        r"\b(cancel|refund).*\b(refund|update|cancel)\b",
    ],
    Intent.ESCALATION: [
        r"\bescalat",
        r"\bmanager\b",
        r"\bsupervisor\b",
        r"\bspeak\b.*\bhuman\b",
        r"\bcomplaint\b",
    ],
    Intent.POLICY: [
        r"\bpolicy\b",
        r"\breturn\b.*\bpolicy\b",
        r"\brefund\b.*\bpolicy\b",
        r"\brules?\b",
        r"\bwhat\b.*\b(return|refund)\b.*\b(window|period|time)\b",
        # Catch "how long to return/refund/exchange"
        r"\bhow\b.*\b(long|many\s+days)\b.*\b(return|refund|exchange)\b",
        # Catch "can I return/refund/exchange/cancel"
        r"\bcan\s+i\b.*\b(return|refund|exchange|cancel)\b",
        # Catch "eligible/eligibility"
        r"\beligib",
        # Catch "warranty/warranties"
        r"\bwarrant",
        # Catch "FAQ"
        r"\bfaq\b",
        # Catch "return/refund window/period/days/deadline"
        r"\b(return|refund)\b.*\b(window|period|days|deadline)\b",
        # Catch "what is the shipping/return/refund/cancellation..."
        r"\bwhat\s+(is|are)\b.*\b(shipping|return|refund|cancellation|exchange|warranty)\b",
        # Catch "how do I return/refund/exchange/cancel/warranty claim"
        r"\bhow\s+(do|does|can|to)\b.*\b(return|refund|exchange|cancel|warranty)\b",
        # Catch "how long does shipping/delivery take"
        r"\bhow\s+long\b.*\b(shipping|delivery|deliver)\b",
        # Catch "do you accept/offer/allow returns/exchanges/refunds"
        r"\bdo\s+you\b.*\b(accept|offer|allow|have)\b.*\b(return|exchange|refund|warranty)\b",
        # Catch "damaged/broken/defective/faulty item/product"
        r"\b(damaged|broken|defective|faulty)\b.*\b(item|product|order|laptop|phone)\b",
        # Catch "money back"
        r"\bmoney\s+back\b",
    ],
}


def classify_intent(query: str) -> Intent:
    """
    Classify user query into an intent category.

    Uses regex-based keyword matching for speed and determinism.
    Falls back to GENERAL if no pattern matches.

    Handles mixed-intent queries (e.g. tracking + policy) by detecting
    when multiple intent signals are present and routing as COMPOUND.

    Args:
        query: The raw user query string.

    Returns:
        Intent enum value.
    """
    query_lower = query.lower().strip()

    # Check COMPOUND first (it often contains tracking/cancel keywords too)
    for pattern in INTENT_PATTERNS[Intent.COMPOUND]:
        if re.search(pattern, query_lower):
            logger.info("Intent classified", intent="COMPOUND", query=query_lower)
            return Intent.COMPOUND

    # Cross-intent detection: if BOTH tracking and policy signals are present,
    # treat as COMPOUND so the planner generates steps for both tools.
    has_tracking = any(
        re.search(p, query_lower) for p in INTENT_PATTERNS[Intent.TRACKING]
    )
    has_policy = any(
        re.search(p, query_lower) for p in INTENT_PATTERNS[Intent.POLICY]
    )
    if has_tracking and has_policy:
        logger.info("Intent classified", intent="COMPOUND", query=query_lower, reason="mixed_tracking_policy")
        return Intent.COMPOUND

    # Also detect tracking + refund-action intent (e.g. "status of ORD-X and refund")
    has_refund_action = bool(re.search(r"\b(refund|money\s+back)\b", query_lower))
    has_order_id = bool(re.search(r"\bORD-\w+\b", query_lower, re.IGNORECASE))
    if has_tracking and has_refund_action and has_order_id:
        logger.info("Intent classified", intent="COMPOUND", query=query_lower, reason="mixed_tracking_refund")
        return Intent.COMPOUND

    # Check other intents in priority order
    for intent in [Intent.TRACKING, Intent.ESCALATION, Intent.POLICY]:
        for pattern in INTENT_PATTERNS[intent]:
            if re.search(pattern, query_lower):
                logger.info("Intent classified", intent=intent.value, query=query_lower)
                return intent

    logger.info("Intent classified", intent="GENERAL", query=query_lower)
    return Intent.GENERAL


def extract_entities(query: str) -> Dict[str, Optional[str]]:
    """
    Extract structured entities from user query.

    Pulls out order IDs, amounts, addresses, and item references
    using regex patterns. This provides structured input for the planner.

    Args:
        query: The raw user query string.

    Returns:
        Dictionary with extracted entity values (or None if not found).
    """
    entities: Dict[str, Optional[str]] = {
        "order_id": None,
        "amount": None,
        "item_index": None,
        "new_address": None,
    }

    # Extract order ID (e.g., ORD-J1, ORD-78321)
    order_match = re.search(r"\b(ORD-\w+)\b", query, re.IGNORECASE)
    if order_match:
        entities["order_id"] = order_match.group(1).upper()

    # Extract amount (e.g., 85000, Rs.25000, 42,000)
    amount_match = re.search(r"(?:Rs\.?\s*|INR\s*)?(\d[\d,]*)\b", query)
    if amount_match:
        amount_str = amount_match.group(1).replace(",", "")
        # Only treat as amount if it's a reasonable number (not an order suffix)
        try:
            val = int(amount_str)
            if val >= 100:  # Ignore small numbers that are likely item indices
                entities["amount"] = str(val)
        except ValueError:
            pass

    # Extract item index (e.g., "item 1", "item 2")
    item_match = re.search(r"\bitem\s+(\d+)\b", query, re.IGNORECASE)
    if item_match:
        entities["item_index"] = item_match.group(1)

    # Extract address (text after "address to" or "address:")
    address_match = re.search(
        r"\baddress\s+(?:to|:)\s+(.+?)(?:\.|,\s*and|\s*$)", query, re.IGNORECASE
    )
    if address_match:
        entities["new_address"] = address_match.group(1).strip().rstrip(".")

    return entities
