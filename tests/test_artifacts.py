import pytest

from src.common.artifacts import (
    ArtifactStore,
    ArtifactIntegrityError,
)

@pytest.fixture
def store():
    return ArtifactStore()

def test_same_content_deduplicates(store):
    content = b"same-data"

    a1 = store.store_artifact(
        "report.json",
        content,
    )

    a2 = store.store_artifact(
        "another.json",
        content,
    )

    assert (
        a1["blob_ref"]
        == a2["blob_ref"]
    )

def test_same_name_different_content_creates_new_blob(
    store,
):
    a1 = store.store_artifact(
        "report.json",
        b"content-one",
    )

    a2 = store.store_artifact(
        "report.json",
        b"content-two",
    )

    assert (
        a1["blob_ref"]
        != a2["blob_ref"]
    )

def test_digest_mismatch_rejected(store):
    with pytest.raises(
        ArtifactIntegrityError
    ):
        store.store_artifact(
            "bad.txt",
            b"real-content",
            metadata={
                "content_digest": "fake"
            },
        )

def test_blob_reference_spoof_rejected(store):
    with pytest.raises(
        ArtifactIntegrityError
    ):
        store.store_artifact(
            "bad.txt",
            b"real-content",
            metadata={
                "blob_ref": "sha256:spoof"
            },
        )

def test_verified_digest_persisted(store):
    artifact = store.store_artifact(
        "safe.txt",
        b"verified",
    )

    assert (
        artifact["content_digest"]
        is not None
    )

def test_blob_content_retrieval(store):
    artifact = store.store_artifact(
        "doc.txt",
        b"hello",
    )

    blob = store.get_blob(
        artifact["blob_ref"]
    )

    assert blob == b"hello"
