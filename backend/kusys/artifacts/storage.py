from __future__ import annotations

import hashlib
import mimetypes
import uuid
from pathlib import Path
from sqlalchemy.orm import Session

from kusys.common.config import get_settings
from kusys.persistence.models import FileArtifact

settings = get_settings()


class LocalStorage:
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root or settings.storage_path).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if self.root not in p.parents and p != self.root:
            raise ValueError("invalid storage key")
        return p

    def put_bytes(self, data: bytes, *, tenant_id: uuid.UUID, project_id: uuid.UUID | None, filename: str, mime_type: str | None = None) -> tuple[FileArtifact, Path]:
        sha = hashlib.sha256(data).hexdigest()
        safe_name = Path(filename).name.replace("/", "_").replace("\\", "_")
        key = f"{tenant_id}/{project_id or 'global'}/{uuid.uuid4()}-{safe_name}"
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        artifact = FileArtifact(
            tenant_id=tenant_id,
            project_id=project_id,
            filename=safe_name,
            mime_type=mime_type or mimetypes.guess_type(safe_name)[0] or "application/octet-stream",
            size_bytes=len(data),
            sha256=sha,
            storage_key=key,
            status="available",
        )
        return artifact, path

    def read(self, artifact: FileArtifact) -> bytes:
        return self._path(artifact.storage_key).read_bytes()

    def path(self, storage_key: str) -> Path:
        return self._path(storage_key)


storage = LocalStorage()


def persist_bytes(db: Session, data: bytes, *, tenant_id: uuid.UUID, project_id: uuid.UUID | None, filename: str, mime_type: str | None = None) -> FileArtifact:
    artifact, _ = storage.put_bytes(data, tenant_id=tenant_id, project_id=project_id, filename=filename, mime_type=mime_type)
    db.add(artifact)
    db.flush()
    return artifact
