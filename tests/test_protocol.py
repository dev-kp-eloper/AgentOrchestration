import pytest
import time
import logging
from src.orchestrator.protocol import (
    WorkerProtocolSettings,
    WorkerProtocolValidator,
    ProtocolValidationError,
    create_validator_with_defaults,
)


class TestWorkerProtocolValidator:
    def test_valid_settings(self):
        settings = WorkerProtocolSettings(ack_timeout=30.0, visibility_timeout=60.0)
        validator = WorkerProtocolValidator(settings)
        assert validator.settings.ack_timeout == 30.0
        assert validator.settings.visibility_timeout == 60.0

    def test_invalid_settings_strict_raises_error(self):
        settings = WorkerProtocolSettings(
            ack_timeout=60.0,
            visibility_timeout=30.0,
            strict_mode=True,
        )
        with pytest.raises(ProtocolValidationError) as excinfo:
            WorkerProtocolValidator(settings)
        assert "Protocol settings invariant violation" in str(excinfo.value)

    def test_invalid_settings_non_strict_logs_warning(self, caplog):
        settings = WorkerProtocolSettings(
            ack_timeout=60.0,
            visibility_timeout=30.0,
            strict_mode=False,
        )
        with caplog.at_level(logging.WARNING):
            validator = WorkerProtocolValidator(settings)
        assert any("Protocol settings invariant violation" in record.message for record in caplog.records)
        assert validator.settings.ack_timeout == 60.0

    def test_validate_task_claim_valid(self):
        settings = WorkerProtocolSettings(ack_timeout=30.0, visibility_timeout=60.0)
        validator = WorkerProtocolValidator(settings)
        now = time.time()
        # Elapsed: 10s (both less than 30 and 60)
        assert validator.validate_task_claim(claim_time=now - 10.0, now=now) is True

    def test_validate_task_claim_exceeds_ack_timeout(self):
        settings = WorkerProtocolSettings(ack_timeout=30.0, visibility_timeout=60.0)
        validator = WorkerProtocolValidator(settings)
        now = time.time()
        # Elapsed: 45s (exceeds ack_timeout but not visibility_timeout)
        assert validator.validate_task_claim(claim_time=now - 45.0, now=now) is False

    def test_validate_task_claim_exceeds_visibility_timeout(self):
        settings = WorkerProtocolSettings(ack_timeout=30.0, visibility_timeout=60.0)
        validator = WorkerProtocolValidator(settings)
        now = time.time()
        # Elapsed: 70s (exceeds both timeouts)
        assert validator.validate_task_claim(claim_time=now - 70.0, now=now) is False

    def test_validate_task_claim_future_time(self):
        settings = WorkerProtocolSettings(ack_timeout=30.0, visibility_timeout=60.0)
        validator = WorkerProtocolValidator(settings)
        now = time.time()
        # Claim is in the future
        assert validator.validate_task_claim(claim_time=now + 5.0, now=now) is False

    def test_create_validator_with_defaults(self):
        validator = create_validator_with_defaults()
        assert validator.settings.ack_timeout == 30.0
        assert validator.settings.visibility_timeout == 60.0
        assert validator.settings.strict_mode is True
