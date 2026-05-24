"""Content-addressed artifact storage."""

import hashlib
import threading
import time
from dataclasses import dataclass
from typing import Dict, Optional

class ArtifactIntegrityError(Exception):
    pass

@dataclass(frozen=True)
class BlobRef:
    digest: str
    blob_id: str
    size: int
    created_at: float

class ArtifactStore:
    """
    Immutable content-addressed artifact store.
    """

    def __init__(self):
        self._blob_store: Dict[str, bytes] = {}
        self._blob_refs: Dict[str, BlobRef] = {}
        self._artifact_metadata = {}
        self._lock = threading.Lock()

    def compute_digest(
        self,
        content: bytes,
    ) -> str:
        return hashlib.sha256(content).hexdigest()

    def build_blob_ref(
        self,
        digest: str,
    ) -> str:
        return f"sha256:{digest}"

    def verify_metadata_digest(
        self,
        claimed_digest: Optional[str],
        actual_digest: str,
    ):
        if (
            claimed_digest is not None
            and claimed_digest != actual_digest
        ):
            raise ArtifactIntegrityError(
                "Claimed digest does not match uploaded content"
            )

    def store_artifact(
        self,
        artifact_name: str,
        content: bytes,
        metadata: Optional[Dict] = None,
    ) -> Dict:
        metadata = metadata or {}

        with self._lock:
            digest = self.compute_digest(content)

            # verify BEFORE dedupe
            self.verify_metadata_digest(
                metadata.get("content_digest"),
                digest,
            )

            blob_ref = self.build_blob_ref(digest)

            # reject suspicious blob reuse
            claimed_blob = metadata.get("blob_ref")

            if (
                claimed_blob is not None
                and claimed_blob != blob_ref
            ):
                raise ArtifactIntegrityError(
                    "Blob reference mismatch"
                )

            # immutable blob creation
            if blob_ref not in self._blob_store:
                self._blob_store[blob_ref] = content

                self._blob_refs[blob_ref] = BlobRef(
                    digest=digest,
                    blob_id=blob_ref,
                    size=len(content),
                    created_at=time.time(),
                )

            artifact_id = (
                f"{artifact_name}:{time.time_ns()}"
            )

            artifact_record = {
                "artifact_id": artifact_id,
                "artifact_name": artifact_name,
                "blob_ref": blob_ref,
                "content_digest": digest,
                "size": len(content),
                "created_at": time.time(),
                "storage_strategy": "content-addressed",
            }

            self._artifact_metadata[
                artifact_id
            ] = artifact_record

            return artifact_record

    def get_blob(
        self,
        blob_ref: str,
    ) -> bytes:
        return self._blob_store[blob_ref]

    def get_blob_metadata(
        self,
        blob_ref: str,
    ) -> BlobRef:
        return self._blob_refs[blob_ref]
