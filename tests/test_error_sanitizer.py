from src.common.error_sanitizer import (
    sanitize_exception_context,
    build_safe_exception_event,
)

def test_payload_is_removed():
    context = {
        "task_id": "abc",
        "payload": {
            "secret": "123",
            "data": "sensitive",
        },
    }

    sanitized = sanitize_exception_context(context)

    assert "payload" not in sanitized

def test_nested_sensitive_fields_removed():
    context = {
        "task_id": "abc",
        "meta": {
            "headers": {
                "authorization": "token",
            },
            "safe": {
                "retry_count": 3,
            },
        },
    }

    sanitized = sanitize_exception_context(context)

    assert "headers" not in sanitized["meta"]

def test_locals_are_removed():
    context = {
        "locals": {
            "password": "secret",
        },
        "task_id": "xyz",
    }

    sanitized = sanitize_exception_context(context)

    assert "locals" not in sanitized

def test_error_class_preserved():
    exc = ValueError("boom")

    event = build_safe_exception_event(
        task_id="task-1",
        exc=exc,
        context={
            "payload": {
                "secret": "hidden",
            }
        },
    )

    assert event["task_id"] == "task-1"
    assert event["error_class"] == "ValueError"
    assert "payload" not in event["context"]

def test_recursive_sanitization():
    context = {
        "task_id": "task-22",
        "nested": {
            "response": {
                "body": "secret",
            },
            "inner": {
                "retry_count": 2,
            },
        },
    }

    sanitized = sanitize_exception_context(context)

    assert "response" not in sanitized["nested"]
