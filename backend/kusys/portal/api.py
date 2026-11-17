from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from kusys.auth.service import Actor, require_actor, require_csrf, require_project_access
from kusys.persistence.database import get_db
from kusys.persistence.models import ClarificationItem, ClarificationRevision, Offer, OfferResponse, OfferVersion, Project, PublishedArtifact

router = APIRouter(prefix="/portal", tags=["customer-portal"])


class ClarificationAnswer(BaseModel):
    answer: str


class OfferReply(BaseModel):
    body: str = Field(min_length=1, max_length=10000)


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
    offer_rows = db.execute(
        select(OfferVersion, Offer, PublishedArtifact.file_artifact_id)
        .join(Offer, Offer.id == OfferVersion.offer_id)
        .join(PublishedArtifact, PublishedArtifact.offer_version_id == OfferVersion.id)
        .where(
            Offer.project_id == project_id,
            Offer.deleted_at.is_(None),
            OfferVersion.status.in_(["freigegeben", "versendet", "angenommen"]),
            PublishedArtifact.immutable.is_(True),
            PublishedArtifact.kind == "docx",
        )
        .order_by(Offer.offer_number, OfferVersion.version.desc())
    ).all()
    offers = []
    seen_versions = set()
    for version, offer, artifact_id in offer_rows:
        if version.id in seen_versions:
            continue
        seen_versions.add(version.id)
        responses = db.scalars(
            select(OfferResponse)
            .where(OfferResponse.offer_version_id == version.id)
            .order_by(OfferResponse.created_at)
        )
        offers.append({
            "id": str(version.id), "offer_number": offer.offer_number,
            "variant_name": offer.variant_name, "version": version.version,
            "status": version.status, "artifact_id": str(artifact_id),
            "responses": [{
                "id": str(item.id), "author_name": item.author_name,
                "body": item.body, "created_at": item.created_at,
            } for item in responses],
        })
    return {
        "id": str(project.id),
        "project_number": project.project_number,
        "name": project.name,
        "status": project.status,
        "clarifications": clarifications,
        "published_artifacts": published,
        "offers": offers,
    }


@router.post("/offer-versions/{offer_version_id}/responses")
def reply_to_offer(
    offer_version_id: uuid.UUID,
    payload: OfferReply,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_csrf),
):
    version = db.get(OfferVersion, offer_version_id)
    if not version or version.status not in {"freigegeben", "versendet", "angenommen"}:
        raise HTTPException(404, "Freigegebenes Angebot nicht gefunden")
    offer = db.get(Offer, version.offer_id)
    require_project_access(db, actor, offer.project_id, {"customer"})
    published = db.scalar(select(PublishedArtifact.id).where(
        PublishedArtifact.offer_version_id == version.id,
        PublishedArtifact.kind == "docx",
        PublishedArtifact.immutable.is_(True),
    ).limit(1))
    if not published:
        raise HTTPException(404, "Freigegebenes Angebotsdokument nicht gefunden")
    body = payload.body.strip()
    if not body:
        raise HTTPException(422, "Antwort darf nicht leer sein")
    response = OfferResponse(
        offer_version_id=version.id,
        author_user_id=actor.user.id,
        author_name=actor.user.display_name,
        author_email=actor.user.email,
        channel="portal",
        body=body,
        created_by=actor.user.id,
    )
    db.add(response)
    db.commit()
    db.refresh(response)
    return {"id": str(response.id), "author_name": response.author_name, "body": response.body, "created_at": response.created_at}


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
