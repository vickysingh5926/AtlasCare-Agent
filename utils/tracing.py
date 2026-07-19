import uuid
import time
from datetime import datetime, timezone

def generate_trace_id() -> str:
    return str(uuid.uuid4())

def generate_session_id() -> str:
    return str(uuid.uuid4())

def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()
