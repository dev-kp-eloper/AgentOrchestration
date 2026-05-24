"""
Exception context sanitizer.

Ensures raw payloads, locals, secrets, and request data
are never attached to exception telemetry.
"""

from typing import Any, Dict

SAFE_FIELDS = {
    "task_id",
    "error_class",
    "error_code",
    "status",
    "retry_count",
}

BLOCKED_KEYS = {
    "payload",
    "raw_payload",
    "request",
    "response",
    "headers",
    "body",
    "token",
    "secret",
    "password",
    "authorization",
    "cookie",
    "session",
    "locals",
    "local_vars",
    "context",
}

def sanitize_exception_context(data: Any) -> Any:
    """
    Recursively sanitize exception context.
    """

    if isinstance(data, dict):
        sanitized = {}

        for key, value in data.items():
            lowered = key.lower()

            # explicitly blocked
            if lowered in BLOCKED_KEYS:
                continue

            # preserve explicitly safe fields
            if lowered in SAFE_FIELDS:
                sanitized[key] = value
                continue

            # nested objects get sanitized recursively
            if isinstance(value, (dict, list)):
                sanitized[key] = sanitize_exception_context(value)

        return sanitized

    if isinstance(data, list):
        return [
            sanitize_exception_context(item)
            for item in data
            if not isinstance(item, (bytes, bytearray))
        ]

    return None

def build_safe_exception_event(
    task_id: str,
    exc: Exception,
    context: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Build telemetry-safe exception event.
    """

    return {
        "task_id": task_id,
        "error_class": exc.__class__.__name__,
        "context": sanitize_exception_context(context),
    }
