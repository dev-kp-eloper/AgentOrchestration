"""Tests for worker resource request validation — capacity planning (#3638)."""

import pytest
from src.agent.sandbox import ResourceLimits, ResourceValidationError, WorkerClass


class TestResourceLimitsPositiveValueGuard:
    """Non-positive values must be rejected before class checks run."""

    def test_zero_cpu_time_raises(self):
        with pytest.raises(ResourceValidationError, match="cpu_time"):
            ResourceLimits(cpu_time=0, memory_mb=512, disk_mb=100, worker_class=None)

    def test_negative_memory_raises(self):
        with pytest.raises(ResourceValidationError, match="memory_mb"):
            ResourceLimits(cpu_time=60, memory_mb=-1, disk_mb=100, worker_class=None)

    def test_zero_disk_raises(self):
        with pytest.raises(ResourceValidationError, match="disk_mb"):
            ResourceLimits(cpu_time=60, memory_mb=512, disk_mb=0, worker_class=None)


class TestResourceLimitsNoClass:
    """worker_class=None bypasses class minimums but still enforces positive values."""

    def test_no_class_accepts_minimal_positive_values(self):
        limits = ResourceLimits(cpu_time=1, memory_mb=1, disk_mb=1, worker_class=None)
        assert limits.cpu_time == 1
        assert limits.memory_mb == 1
        assert limits.disk_mb == 1
        assert limits.worker_class is None


class TestResourceLimitsLightweight:
    """LIGHTWEIGHT class: cpu>=10, memory>=64, disk>=50."""

    def test_at_minimums_passes(self):
        limits = ResourceLimits(cpu_time=10, memory_mb=64, disk_mb=50, worker_class=WorkerClass.LIGHTWEIGHT)
        assert limits.worker_class == WorkerClass.LIGHTWEIGHT

    def test_cpu_below_minimum_rejected(self):
        with pytest.raises(ResourceValidationError, match="cpu_time"):
            ResourceLimits(cpu_time=9, memory_mb=64, disk_mb=50, worker_class=WorkerClass.LIGHTWEIGHT)

    def test_memory_below_minimum_rejected(self):
        with pytest.raises(ResourceValidationError, match="memory_mb"):
            ResourceLimits(cpu_time=10, memory_mb=63, disk_mb=50, worker_class=WorkerClass.LIGHTWEIGHT)

    def test_disk_below_minimum_rejected(self):
        with pytest.raises(ResourceValidationError, match="disk_mb"):
            ResourceLimits(cpu_time=10, memory_mb=64, disk_mb=49, worker_class=WorkerClass.LIGHTWEIGHT)

    def test_above_minimums_passes(self):
        limits = ResourceLimits(cpu_time=20, memory_mb=128, disk_mb=100, worker_class=WorkerClass.LIGHTWEIGHT)
        assert limits.cpu_time == 20


class TestResourceLimitsStandard:
    """STANDARD class (default): cpu>=30, memory>=256, disk>=100."""

    def test_default_worker_class_is_standard(self):
        limits = ResourceLimits()
        assert limits.worker_class == WorkerClass.STANDARD

    def test_at_minimums_passes(self):
        limits = ResourceLimits(cpu_time=30, memory_mb=256, disk_mb=100)
        assert limits.cpu_time == 30

    def test_cpu_below_minimum_rejected(self):
        with pytest.raises(ResourceValidationError, match="cpu_time"):
            ResourceLimits(cpu_time=29, memory_mb=256, disk_mb=100)

    def test_memory_below_minimum_rejected(self):
        with pytest.raises(ResourceValidationError, match="memory_mb"):
            ResourceLimits(cpu_time=30, memory_mb=255, disk_mb=100)

    def test_error_message_includes_class_name(self):
        with pytest.raises(ResourceValidationError, match="standard"):
            ResourceLimits(cpu_time=1, memory_mb=1, disk_mb=1)


class TestResourceLimitsHeavy:
    """HEAVY class: cpu>=60, memory>=512, disk>=200."""

    def test_at_minimums_passes(self):
        limits = ResourceLimits(cpu_time=60, memory_mb=512, disk_mb=200, worker_class=WorkerClass.HEAVY)
        assert limits.disk_mb == 200

    def test_disk_below_minimum_rejected(self):
        with pytest.raises(ResourceValidationError, match="disk_mb"):
            ResourceLimits(cpu_time=60, memory_mb=512, disk_mb=199, worker_class=WorkerClass.HEAVY)

    def test_multiple_violations_reported(self):
        """All violations must appear in the error message."""
        with pytest.raises(ResourceValidationError) as exc_info:
            ResourceLimits(cpu_time=1, memory_mb=1, disk_mb=1, worker_class=WorkerClass.HEAVY)
        msg = str(exc_info.value)
        assert "cpu_time" in msg
        assert "memory_mb" in msg
        assert "disk_mb" in msg
