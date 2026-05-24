"""Tests for registry namespace and tag validation — release script (#3688)."""

import pytest
from src.sdk.registry import (
    RegistryValidationError,
    parse_image_ref,
    validate_tag,
    validate_registry_namespace,
)

ALLOWLIST = ["ghcr.io/orchestration-agent", "registry.example.com/agents"]


class TestParseImageRef:
    def test_valid_ref_returns_components(self):
        host, ns, name = parse_image_ref("ghcr.io/orchestration-agent/api:v1.0.0")
        assert host == "ghcr.io"
        assert ns == "orchestration-agent"
        assert name == "api:v1.0.0"

    def test_missing_tag_raises(self):
        with pytest.raises(RegistryValidationError, match="missing tag"):
            parse_image_ref("ghcr.io/orchestration-agent/api")

    def test_missing_namespace_raises(self):
        with pytest.raises(RegistryValidationError, match="namespace"):
            parse_image_ref("ghcr.io/api:v1.0.0")


class TestValidateTag:
    def test_valid_semver_passes(self):
        for tag in ("v1.2.3", "1.2.3", "v0.0.1", "v1.2.3-alpha.1", "v1.2.3+build.42"):
            validate_tag(tag)  # must not raise

    def test_latest_tag_rejected(self):
        with pytest.raises(RegistryValidationError, match="latest"):
            validate_tag("latest")

    def test_empty_tag_rejected(self):
        with pytest.raises(RegistryValidationError, match="empty"):
            validate_tag("")

    def test_non_semver_tag_rejected(self):
        for bad in ("main", "sha-abc1234", "release", "SNAPSHOT"):
            with pytest.raises(RegistryValidationError, match="semver"):
                validate_tag(bad)


class TestValidateRegistryNamespace:
    def test_approved_namespace_passes(self):
        validate_registry_namespace(
            "ghcr.io/orchestration-agent/api:v1.2.3", allowlist=ALLOWLIST
        )

    def test_second_approved_namespace_passes(self):
        validate_registry_namespace(
            "registry.example.com/agents/worker:v2.0.0", allowlist=ALLOWLIST
        )

    def test_unapproved_namespace_raises(self):
        with pytest.raises(RegistryValidationError, match="allowlist"):
            validate_registry_namespace(
                "docker.io/attacker/api:v1.0.0", allowlist=ALLOWLIST
            )

    def test_unapproved_host_same_namespace_raises(self):
        """Different host with same namespace must still be rejected."""
        with pytest.raises(RegistryValidationError, match="allowlist"):
            validate_registry_namespace(
                "evil.io/orchestration-agent/api:v1.0.0", allowlist=ALLOWLIST
            )

    def test_latest_tag_rejected_before_namespace_check(self):
        with pytest.raises(RegistryValidationError, match="latest"):
            validate_registry_namespace(
                "ghcr.io/orchestration-agent/api:latest", allowlist=ALLOWLIST
            )

    def test_invalid_tag_rejected(self):
        with pytest.raises(RegistryValidationError, match="semver"):
            validate_registry_namespace(
                "ghcr.io/orchestration-agent/api:main", allowlist=ALLOWLIST
            )

    def test_empty_allowlist_blocks_everything(self):
        with pytest.raises(RegistryValidationError, match="allowlist"):
            validate_registry_namespace(
                "ghcr.io/orchestration-agent/api:v1.0.0", allowlist=[]
            )

    def test_error_message_includes_approved_list(self):
        with pytest.raises(RegistryValidationError, match="orchestration-agent"):
            validate_registry_namespace(
                "docker.io/rogue/api:v1.0.0", allowlist=ALLOWLIST
            )

    def test_env_var_allowlist_used_when_none(self, monkeypatch):
        monkeypatch.setenv("AO_REGISTRY_ALLOWLIST", "myregistry.io/myorg")
        validate_registry_namespace("myregistry.io/myorg/svc:v3.0.0")

    def test_env_var_blocks_unlisted_when_set(self, monkeypatch):
        monkeypatch.setenv("AO_REGISTRY_ALLOWLIST", "myregistry.io/myorg")
        with pytest.raises(RegistryValidationError):
            validate_registry_namespace("ghcr.io/orchestration-agent/api:v1.0.0")
