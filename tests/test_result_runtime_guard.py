import threading
import pytest

from src.runtime.result_guard import (
    ResultRuntimeGuard,
    RuntimeState,
    ResultSerializationError,
)

class NonSerializable:
    pass

def test_serializable_result_succeeds():
    guard = ResultRuntimeGuard()
    guard.initialize("run-1")
    result = guard.complete_run(
        "run-1",
        {
            "ok": True,
        },
    )
    assert result["state"] == RuntimeState.SUCCEEDED

def test_non_serializable_result_fails_closed():
    guard = ResultRuntimeGuard()
    guard.initialize("run-2")
    with pytest.raises(ResultSerializationError):
        guard.complete_run(
            "run-2",
            {
                "bad": NonSerializable(),
            },
        )

def test_duplicate_completion_is_idempotent():
    guard = ResultRuntimeGuard()
    guard.initialize("run-3")
    first = guard.complete_run(
        "run-3",
        {
            "ok": True,
        },
    )
    second = guard.complete_run(
        "run-3",
        {
            "changed": False,
        },
    )
    assert first == second

def test_terminal_state_recorded_once():
    guard = ResultRuntimeGuard()
    guard.initialize("run-4")
    guard.complete_run(
        "run-4",
        {
            "done": True,
        },
    )
    assert guard._states["run-4"] == RuntimeState.SUCCEEDED

def test_concurrent_completion_safe():
    guard = ResultRuntimeGuard()
    guard.initialize("run-5")
    results = []

    def worker():
        result = guard.complete_run(
            "run-5",
            {
                "safe": True,
            },
        )
        results.append(result)

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(results) == 5
    terminal = guard._terminal_results["run-5"]
    assert terminal["state"] == RuntimeState.SUCCEEDED

def test_failed_run_is_terminal():
    guard = ResultRuntimeGuard()
    guard.initialize("run-6")
    guard.fail_run("run-6", "worker_crash")
    assert guard._states["run-6"] == RuntimeState.FAILED
