"""Agent Sandbox — Isolated execution environment for agents."""

import os
import tempfile
try:
    import resource
except ImportError:
    resource = None
from enum import Enum
from typing import Dict, Optional
from pathlib import Path


class ResourceValidationError(ValueError):
    """Raised when resource requests fall below workload-class minimums."""
    pass


class WorkerClass(str, Enum):
    """Workload classes with documented minimum resource requirements.

    Minimums per class
    ------------------
    LIGHTWEIGHT : cpu_time >= 10 s,  memory_mb >=  64 MB,  disk_mb >=  50 MB
    STANDARD    : cpu_time >= 30 s,  memory_mb >= 256 MB,  disk_mb >= 100 MB
    HEAVY       : cpu_time >= 60 s,  memory_mb >= 512 MB,  disk_mb >= 200 MB
    """
    LIGHTWEIGHT = "lightweight"
    STANDARD = "standard"
    HEAVY = "heavy"


# Per-class minimums: cpu_time (s), memory_mb, disk_mb
_CLASS_MINIMUMS: Dict[str, Dict[str, int]] = {
    WorkerClass.LIGHTWEIGHT: {"cpu_time": 10,  "memory_mb":  64, "disk_mb":  50},
    WorkerClass.STANDARD:    {"cpu_time": 30,  "memory_mb": 256, "disk_mb": 100},
    WorkerClass.HEAVY:       {"cpu_time": 60,  "memory_mb": 512, "disk_mb": 200},
}


class ResourceLimits:
    """Resource limits for a worker, validated against workload-class minimums.

    Parameters
    ----------
    cpu_time:     Maximum CPU seconds the worker may consume.
    memory_mb:    Maximum resident memory in mebibytes.
    disk_mb:      Maximum temporary-disk usage in mebibytes.
    worker_class: Workload class that determines minimum acceptable values.
                  Pass ``None`` to skip class-based validation (not recommended
                  for production deployments).

    Raises
    ------
    ResourceValidationError
        If any requested value is non-positive or below the class minimum.
    """

    def __init__(
        self,
        cpu_time: int = 60,
        memory_mb: int = 512,
        disk_mb: int = 100,
        worker_class: Optional[WorkerClass] = WorkerClass.STANDARD,
    ):
        errors = []
        # Positive value guards
        if not isinstance(cpu_time, int) or cpu_time <= 0:
            errors.append(f"cpu_time must be a positive integer, got {cpu_time!r}")
        if not isinstance(memory_mb, int) or memory_mb <= 0:
            errors.append(f"memory_mb must be a positive integer, got {memory_mb!r}")
        if not isinstance(disk_mb, int) or disk_mb <= 0:
            errors.append(f"disk_mb must be a positive integer, got {disk_mb!r}")
        if errors:
            raise ResourceValidationError("; ".join(errors))

        # Workload-class minimum enforcement
        if worker_class is not None:
            mins = _CLASS_MINIMUMS[worker_class]
            if cpu_time < mins["cpu_time"]:
                errors.append(
                    f"cpu_time={cpu_time}s is below {worker_class.value!r} minimum "
                    f"of {mins['cpu_time']}s"
                )
            if memory_mb < mins["memory_mb"]:
                errors.append(
                    f"memory_mb={memory_mb} is below {worker_class.value!r} minimum "
                    f"of {mins['memory_mb']} MB"
                )
            if disk_mb < mins["disk_mb"]:
                errors.append(
                    f"disk_mb={disk_mb} is below {worker_class.value!r} minimum "
                    f"of {mins['disk_mb']} MB"
                )
            if errors:
                raise ResourceValidationError(
                    f"Worker resource requests rejected "
                    f"(class={worker_class.value!r}): " + "; ".join(errors)
                )

        self.cpu_time = cpu_time
        self.memory_mb = memory_mb
        self.disk_mb = disk_mb
        self.worker_class = worker_class


class AgentSandbox:
    def __init__(self, base_path: Optional[str] = None):
        self.base_path = Path(base_path or tempfile.mkdtemp(prefix="ao_sandbox_"))
        self._sandboxes: Dict[str, Path] = {}

    def create(self, agent_id: str, limits: Optional[ResourceLimits] = None) -> Path:
        sandbox_path = self.base_path / agent_id
        sandbox_path.mkdir(parents=True, exist_ok=True)
        self._sandboxes[agent_id] = sandbox_path
        return sandbox_path

    def destroy(self, agent_id: str) -> bool:
        sandbox = self._sandboxes.pop(agent_id, None)
        if sandbox and sandbox.exists():
            import shutil
            shutil.rmtree(sandbox, ignore_errors=True)
            return True
        return False

    def get_path(self, agent_id: str) -> Optional[Path]:
        return self._sandboxes.get(agent_id)

    def apply_limits(self, agent_id: str, limits: ResourceLimits) -> None:
        if resource is None:
            return
        try:
            resource.setrlimit(resource.RLIMIT_CPU, (limits.cpu_time, limits.cpu_time))
            mem_bytes = limits.memory_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
        except (ValueError, Exception):
            pass

    def cleanup_all(self) -> None:
        for agent_id in list(self._sandboxes.keys()):
            self.destroy(agent_id)
