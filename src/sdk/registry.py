"""Registry namespace and image tag validation for release push scripts.

This module enforces that Docker image push targets are pre-approved
before any authentication or upload begins, preventing images from
being accidentally published to unintended registries or namespaces.

Configuration
-------------
Set ``AO_REGISTRY_ALLOWLIST`` to a comma-separated list of approved
``<host>/<namespace>`` prefixes, e.g.::

    AO_REGISTRY_ALLOWLIST=ghcr.io/orchestration-agent,registry.example.com/agents

If the env var is absent or empty the module falls back to the compile-time
``DEFAULT_REGISTRY_ALLOWLIST`` constant which is intentionally restrictive.
"""

import os
import re
import logging
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# Compile-time default — operators should override via AO_REGISTRY_ALLOWLIST.
DEFAULT_REGISTRY_ALLOWLIST: List[str] = [
    "ghcr.io/orchestration-agent",
]

# Semver tag pattern: v1.2.3 or 1.2.3 (with optional pre-release / build metadata)
_TAG_RE = re.compile(
    r"^v?\d+\.\d+\.\d+"           # major.minor.patch
    r"(?:-[a-zA-Z0-9._-]+)?"      # optional pre-release
    r"(?:\+[a-zA-Z0-9._-]+)?$"   # optional build metadata
)


class RegistryValidationError(ValueError):
    """Raised when an image push target fails namespace or tag validation."""
    pass


def _load_allowlist() -> List[str]:
    raw = os.environ.get("AO_REGISTRY_ALLOWLIST", "")
    if raw.strip():
        return [ns.strip().rstrip("/") for ns in raw.split(",") if ns.strip()]
    return DEFAULT_REGISTRY_ALLOWLIST


def parse_image_ref(image_ref: str) -> Tuple[str, str, str]:
    """Parse ``<registry>/<namespace>/<name>:<tag>`` into components.

    Returns
    -------
    (registry_host, namespace, name_with_tag)
        e.g. ``("ghcr.io", "orchestration-agent", "api:v1.2.3")``

    Raises
    ------
    RegistryValidationError
        If the reference cannot be parsed into at least host/namespace/name:tag.
    """
    if ":" not in image_ref:
        raise RegistryValidationError(
            f"Image reference missing tag: {image_ref!r}. "
            "Use fully-qualified refs like 'registry/namespace/name:tag'."
        )

    parts = image_ref.split("/")
    if len(parts) < 3:
        raise RegistryValidationError(
            f"Image reference {image_ref!r} must include registry host, namespace, "
            "and image name, e.g. 'ghcr.io/myorg/myimage:v1.0.0'."
        )

    registry_host = parts[0]
    namespace = parts[1]
    name_with_tag = "/".join(parts[2:])
    return registry_host, namespace, name_with_tag


def validate_tag(tag: str) -> None:
    """Ensure the image tag is a valid semver string.

    Raises
    ------
    RegistryValidationError
        If the tag is empty, ``latest``, or not a semver string.
    """
    if not tag:
        raise RegistryValidationError("Image tag must not be empty.")
    if tag == "latest":
        raise RegistryValidationError(
            "Tag 'latest' is not allowed in release pushes. "
            "Use an explicit semver tag like 'v1.2.3'."
        )
    if not _TAG_RE.match(tag):
        raise RegistryValidationError(
            f"Tag {tag!r} is not a valid semver string. "
            "Expected format: 'v<major>.<minor>.<patch>[-pre][+build]'."
        )


def validate_registry_namespace(
    image_ref: str,
    allowlist: Optional[List[str]] = None,
) -> None:
    """Validate that *image_ref* targets an approved registry namespace.

    Both tag validity and namespace membership are checked so callers
    get a single, combined validation call before any push begins.

    Parameters
    ----------
    image_ref:  Fully-qualified image reference, e.g.
                ``ghcr.io/orchestration-agent/api:v1.2.3``.
    allowlist:  Override the namespace allowlist (mainly for tests).
                If ``None``, the allowlist is loaded from the environment.

    Raises
    ------
    RegistryValidationError
        On tag or namespace violations.
    """
    if allowlist is None:
        allowlist = _load_allowlist()

    registry_host, namespace, name_with_tag = parse_image_ref(image_ref)

    # Validate tag first — fail fast before network I/O.
    tag = name_with_tag.rsplit(":", 1)[-1] if ":" in name_with_tag else ""
    validate_tag(tag)

    # Check namespace membership.
    target_prefix = f"{registry_host}/{namespace}"
    if target_prefix not in allowlist:
        logger.warning(
            "Registry push blocked: target=%r not in allowlist=%r",
            target_prefix, allowlist,
        )
        raise RegistryValidationError(
            f"Registry namespace {target_prefix!r} is not in the approved allowlist. "
            f"Approved namespaces: {allowlist}. "
            "Update AO_REGISTRY_ALLOWLIST to add new targets after team review."
        )

    logger.info(
        "Registry push approved: target=%r tag=%r namespace=%r",
        image_ref, tag, target_prefix,
    )
