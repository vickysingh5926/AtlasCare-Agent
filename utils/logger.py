"""
Structured JSON Logger — Production-Grade Observability

Configures structlog for structured JSON logging with:
- ISO-8601 timestamps
- Log level tags
- PII masking (emails, phones, Aadhaar) via custom processor
- JSON output for machine-parseable log aggregation

All modules import `logger` from this module for consistent output.
"""

import structlog
from utils.pii import pii_masking_processor


def setup_logger():
    """
    Configure and return a structured logger with PII masking.

    Processor chain:
    1. Add ISO timestamp
    2. Add log level
    3. Mask PII in all fields
    4. Render as JSON
    """
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.stdlib.add_log_level,
            pii_masking_processor,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
    )
    return structlog.get_logger()


logger = setup_logger()
