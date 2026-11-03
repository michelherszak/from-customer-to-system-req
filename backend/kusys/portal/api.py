from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from kusys.auth.service import Actor, require_actor, require_csrf, require_project_access
from kusys.persistence.database import get_db
from kusys.persistence.models import ClarificationItem, ClarificationRevision, Project, PublishedArtifact

router = APIRouter(prefix="/portal", tags=["customer-portal"])


class ClarificationAnswer(BaseModel):
    answer: str


@router.get("/projects/{project_id}")
def portal_project(project_id: uuid.UUID, db: Session = Depends(get_db), actor: Actor = Depends(require_actor)):
    require_project_access(db, actor, project_id, {"customer"})
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Projekt nicht gefunden")
    clarifications = [
        {"id": str(x.id), "key": x.key, "text": x.text, "status": x.status, "answer": x.answer}
        for x in db.scalars(
            select(ClarificationItem).where(
                ClarificationItem.project_id == project_id,
                ClarificationItem.deleted_at.is_(None),
            )
        )
    ]
    published = [
        {"artifact_id": str(a.file_artifact_id), "kind": a.kind, "language": a.language}
        for a in db.scalars(
            select(PublishedArtifact).where(
                PublishedArtifact.project_id == project_id,
                PublishedArtifact.immutable.is_(True),
            )
        )
    ]
    return {
        "id": str(project.id),
        "project_number": project.project_number,
        "name": project.name,
        "status": project.status,
        "clarifications": clarifications,
        "published_artifacts": published,
    }


@router.post("/clarifications/{clarification_id}/answer")
def answer_clarification(
    clarification_id: uuid.UUID,
    payload: ClarificationAnswer,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_csrf),
):
    item = db.get(ClarificationItem, clarification_id)
    if not item or item.deleted_at is not None:
        raise HTTPException(404, "Klärungspunkt nicht gefunden")
    require_project_access(db, actor, item.project_id, {"customer"})
    if not payload.answer.strip():
        raise HTTPException(422, "Antwort darf nicht leer sein")
    revision_no = (
        db.scalar(
            select(func.max(ClarificationRevision.revision_no)).where(
                ClarificationRevision.clarification_id == item.id
            )
        )
        or 0
    ) + 1
    db.add(
        ClarificationRevision(
            clarification_id=item.id,
            revision_no=revision_no,
            snapshot={"text": item.text, "answer": item.answer, "status": item.status},
            created_by=actor.user.id,
        )
    )
    item.answer = payload.answer.strip()
    item.status = "beantwortet – interne Prüfung ausstehend"
    item.lock_version += 1
    db.commit()
    return {"id": str(item.id), "key": item.key, "status": item.status, "answer": item.answer}
