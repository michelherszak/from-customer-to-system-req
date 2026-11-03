from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from kusys.artifacts.storage import storage
from kusys.auth.service import Actor, require_actor, require_project_access, require_tenant_access
from kusys.persistence.database import get_db
from kusys.persistence.models import FileArtifact, ProjectMembership, PublishedArtifact

router = APIRouter(tags=["artifacts"])


def _customer_can_download(db: Session, actor: Actor, artifact: FileArtifact) -> bool:
    if not artifact.project_id:
        return False
    membership = db.scalar(
        select(ProjectMembership).where(
            ProjectMembership.project_id == artifact.project_id,
            ProjectMembership.user_id == actor.user.id,
            ProjectMembership.role == "customer",
        )
    )
    if not membership:
        return False
    published = db.scalar(
        select(PublishedArtifact).where(
            PublishedArtifact.file_artifact_id == artifact.id,
            PublishedArtifact.project_id == artifact.project_id,
            PublishedArtifact.immutable.is_(True),
        )
    )
    return published is not None


@router.get("/artifacts/{artifact_id}")
def download(artifact_id: uuid.UUID, db: Session = Depends(get_db), actor: Actor = Depends(require_actor)):
    artifact = db.get(FileArtifact, artifact_id)
    # Unknown and unauthorized object IDs intentionally converge on a non-disclosing response.
    if not artifact or artifact.status != "available":
        raise HTTPException(404, "Artefakt nicht gefunden")
    if artifact.project_id:
        try:
            require_project_access(db, actor, artifact.project_id)
        except HTTPException:
            if not _customer_can_download(db, actor, artifact):
                raise HTTPException(403, "Kein Zugriff auf dieses Artefakt")
    else:
        require_tenant_access(db, actor, artifact.tenant_id)
    path = storage.path(artifact.storage_key)
    if not path.exists():
        raise HTTPException(404, "Artefaktdatei fehlt")
    return FileResponse(path, media_type=artifact.mime_type, filename=artifact.filename)
