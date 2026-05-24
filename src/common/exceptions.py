"""Custom exceptions and telemetry tracking integration."""

from typing import Any, Dict, List
from src.common.error_sanitizer import build_safe_exception_event

class ExceptionTracker:
    def __init__(self):
        self._events: List[Dict[str, Any]] = []

    def capture(
        self,
        task_id: str,
        exc: Exception,
        context: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        safe_event = build_safe_exception_event(
            task_id=task_id,
            exc=exc,
            context=context or {},
        )

        self._events.append(safe_event)

        return safe_event
