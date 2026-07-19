"""
PII Masking Utility

Masks Personally Identifiable Information in log output to prevent
sensitive data leakage. Applied as a structlog processor so all
structured logs are automatically sanitized.

Masked patterns:
- Email addresses → ***@***.com
- Indian phone numbers → +91-****XXXX
- Aadhaar numbers → XXXX-XXXX-1234
"""

import re
from typing import Any


# Compiled regex patterns for PII detection
_EMAIL_PATTERN = re.compile(
    r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
)
_PHONE_PATTERN = re.compile(
    r"(\+91[-\s]?)?\d{10}"
)
_AADHAAR_PATTERN = re.compile(
    r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}\b"
)


def mask_pii(value: str) -> str:
    """
    Mask PII patterns in a string.

    Args:
        value: Input string that may contain PII.

    Returns:
        String with PII patterns replaced by masked versions.
    """
    # Mask emails
    value = _EMAIL_PATTERN.sub("***@***.com", value)
    # Mask phone numbers
    value = _PHONE_PATTERN.sub("+91-****XXXX", value)
    # Mask Aadhaar numbers
    value = _AADHAAR_PATTERN.sub("XXXX-XXXX-XXXX", value)
    return value


def mask_pii_in_dict(data: Any) -> Any:
    """
    Recursively mask PII in a dictionary, list, or string.

    Args:
        data: Input data structure (dict, list, str, or primitive).

    Returns:
        Data structure with all string values PII-masked.
    """
    if isinstance(data, str):
        return mask_pii(data)
    elif isinstance(data, dict):
        return {k: mask_pii_in_dict(v) for k, v in data.items()}
    elif isinstance(data, (list, tuple)):
        return [mask_pii_in_dict(item) for item in data]
    return data


def pii_masking_processor(logger: Any, method_name: str, event_dict: dict) -> dict:
    """
    Structlog processor that masks PII in all log event values.

    Attach to structlog's processor chain to automatically sanitize
    all structured log fields before output.
    """
    for key, value in event_dict.items():
        if isinstance(value, str):
            event_dict[key] = mask_pii(value)
        elif isinstance(value, (dict, list)):
            event_dict[key] = mask_pii_in_dict(value)
    return event_dict
