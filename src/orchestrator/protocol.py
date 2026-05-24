"""Worker Protocol Validator — Hardening task claim, ack, and visibility timeouts."""

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


class ProtocolValidationError(ValueError):
    """Raised when protocol settings violate invariants or claim checks fail."""
    pass


@dataclass
class WorkerProtocolSettings:
    """Configuration settings for the queue worker protocol."""
    ack_timeout: float
    visibility_timeout: float
    max_retries: int = 3
    strict_mode: bool = True


class WorkerProtocolValidator:
    """Validates worker protocol settings and task lifecycle transitions (claim, ack, retry)."""

    def __init__(self, settings: WorkerProtocolSettings):
        self.settings = settings
        self.validate_settings()

    def validate_settings(self) -> None:
        """Enforces that ack_timeout is strictly less than visibility_timeout."""
        if self.settings.ack_timeout >= self.settings.visibility_timeout:
            msg = (
                f"Protocol settings invariant violation: ack_timeout ({self.settings.ack_timeout}) "
                f"must be strictly less than visibility_timeout ({self.settings.visibility_timeout}). "
                "Otherwise, tasks could be delivered to multiple workers simultaneously."
            )
            if self.settings.strict_mode:
                raise ProtocolValidationError(msg)
            else:
                logger.warning(msg)

    def validate_task_claim(self, claim_time: float, now: float) -> bool:
        """
        Validates if a task claim is still active or has expired.
        
        Args:
            claim_time: Epoch timestamp when the task was claimed.
            now: Current epoch timestamp.
            
        Returns:
            True if the claim is valid, False otherwise.
        """
        elapsed = now - claim_time
        if elapsed < 0:
            # Clock drift or future claim time is invalid
            logger.error("Task claim verification rejected: claim time is in the future")
            return False

        if elapsed >= self.settings.visibility_timeout:
            logger.info("Task claim verification rejected: claim exceeded visibility timeout")
            return False

        if elapsed >= self.settings.ack_timeout:
            logger.info("Task claim verification rejected: claim exceeded ack timeout")
            return False

        return True


def create_validator_with_defaults(
    ack_timeout: float = 30.0,
    visibility_timeout: float = 60.0,
    strict_mode: bool = True,
) -> WorkerProtocolValidator:
    """Factory function creating a validator with standard defaults."""
    settings = WorkerProtocolSettings(
        ack_timeout=ack_timeout,
        visibility_timeout=visibility_timeout,
        strict_mode=strict_mode,
    )
    return WorkerProtocolValidator(settings)
