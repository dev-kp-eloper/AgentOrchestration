"""Runtime result guards for durable orchestration safety."""

import json
import threading
import time
from enum import Enum
from typing import Any, Dict


class RuntimeState(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETING = "COMPLETING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ResultSerializationError(Exception):
    pass


class InvalidStateTransition(Exception):
    pass


class ResultRuntimeGuard:
    """Durable runtime guard ensuring:
    
    - Idempotent completion
    - Serialization validation
    - Safe terminal transitions
    """

    TERMINAL_STATES = {
        RuntimeState.SUCCEEDED,
        RuntimeState.FAILED,
        RuntimeState.CANCELLED,
    }

    def __init__(self):
        self._states: Dict[str, RuntimeState] = {}
        self._terminal_results = {}
        self._locks = {}
        self._audit = []

    def _lock_for(self, run_id: str):
        if run_id not in self._locks:
            self._locks[run_id] = threading.Lock()
        return self._locks[run_id]

    def initialize(self, run_id: str):
        self._states[run_id] = RuntimeState.RUNNING

    def validate_json_result(self, result: Any):
        try:
            json.dumps(result)
        except Exception as exc:
            raise ResultSerializationError(
                f"Result is not JSON serializable: {exc}"
            ) from exc

    def transition_to_completing(self, run_id: str):
        current = self._states.get(run_id)
        if current != RuntimeState.RUNNING:
            raise InvalidStateTransition(
                f"Cannot complete run from state {current}"
            )
        self._states[run_id] = RuntimeState.COMPLETING

    def commit_terminal_state(
        self,
        run_id: str,
        result: Any,
        state: RuntimeState = RuntimeState.SUCCEEDED,
    ):
        if state not in self.TERMINAL_STATES:
            raise InvalidStateTransition(f"{state} is not terminal")
        self._terminal_results[run_id] = {
            "state": state,
            "committed_at": time.time(),
        }
        self._states[run_id] = state

    def complete_run(self, run_id: str, result: Any):
        lock = self._lock_for(run_id)
        with lock:
            current = self._states.get(run_id)

            # idempotent completion
            if current in self.TERMINAL_STATES:
                return self._terminal_results[run_id]

            # fail closed BEFORE mutations
            self.validate_json_result(result)

            # durable transition
            self.transition_to_completing(run_id)

            # persist success
            self.commit_terminal_state(
                run_id,
                result,
                RuntimeState.SUCCEEDED,
            )

            self._audit.append(
                {
                    "run_id": run_id,
                    "state": "SUCCEEDED",
                    "timestamp": time.time(),
                }
            )

            return self._terminal_results[run_id]

    def fail_run(self, run_id: str, reason: str):
        lock = self._lock_for(run_id)
        with lock:
            current = self._states.get(run_id)
            if current in self.TERMINAL_STATES:
                return
            self.commit_terminal_state(
                run_id,
                {"reason": reason},
                RuntimeState.FAILED,
            )
