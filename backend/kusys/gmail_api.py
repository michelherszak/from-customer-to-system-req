from __future__ import annotations

import base64
import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import parseaddr
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from kusys.artifacts.storage import storage
from kusys.auth.service import Actor, require_actor, require_project_access, require_csrf
from kusys.common.config import get_settings
from kusys.common.security import decrypt_secret, encrypt_secret, utcnow
from kusys.persistence.database import get_db
from kusys.persistence.models import (
    FileArtifact, GmailConnection, GmailOfferThread, Offer, OfferResponse, OfferVersion, Project,
    ProjectMembership, PublishedArtifact, TenantMembership, User,
)

router = APIRouter(tags=["gmail"])
settings = get_settings()
SCOPES = "https://www.googleapis.com/auth/gmail.compose https://www.googleapis.com/auth/gmail.readonly"


class EmailDraftRequest(BaseModel):
    to: str = Field(min_length=3, max_length=320)
    subject: str = Field(min_length=1, max_length=998)
    body: str = Field(min_length=1, max_length=20000)


def _state_token(project_id: uuid.UUID, tenant_id: uuid.UUID, user_id: uuid.UUID) -> str:
    payload = json.dumps({"project": str(project_id), "tenant": str(tenant_id), "user": str(user_id), "exp": int(utcnow().timestamp()) + 600}, separators=(",", ":")).encode()
    encoded = base64.urlsafe_b64encode(payload).decode().rstrip("=")
    signature = hmac.new(settings.master_key.encode(), encoded.encode(), hashlib.sha256).digest()
    return encoded + "." + base64.urlsafe_b64encode(signature).decode().rstrip("=")


def _read_state(state: str) -> dict:
    try:
        encoded, signature = state.split(".", 1)
        expected = hmac.new(settings.master_key.encode(), encoded.encode(), hashlib.sha256).digest()
        supplied = base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4))
        if not hmac.compare_digest(expected, supplied):
            raise ValueError("signature")
        payload = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        result = json.loads(payload)
        if int(result["exp"]) < int(utcnow().timestamp()):
            raise ValueError("expired")
        return result
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise HTTPException(400, "Gmail-Verknüpfung abgelaufen oder ungültig") from None


def _request_json(url: str, *, method: str = "GET", data: dict | None = None, token: str | None = None) -> dict:
    headers = {"Accept": "application/json"}
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read())
    except HTTPError as exc:
        detail = exc.read(2048).decode("utf-8", "replace")
        raise HTTPException(502, f"Gmail API antwortete mit HTTP {exc.code}: {detail[:500]}") from None
    except (TimeoutError, URLError, OSError):
        raise HTTPException(502, "Gmail API ist momentan nicht erreichbar") from None


def _exchange_code(code: str) -> dict:
    request = Request(
        "https://oauth2.googleapis.com/token",
        data=urlencode({
            "code": code, "client_id": settings.gmail_client_id,
            "client_secret": settings.gmail_client_secret,
            "redirect_uri": settings.gmail_redirect_uri, "grant_type": "authorization_code",
        }).encode(),
        headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read())
    except (HTTPError, TimeoutError, URLError, OSError):
        raise HTTPException(502, "Gmail-OAuth konnte nicht abgeschlossen werden") from None


def _access_token(connection: GmailConnection) -> str:
    request = Request(
        "https://oauth2.googleapis.com/token",
        data=urlencode({
            "client_id": settings.gmail_client_id,
            "client_secret": settings.gmail_client_secret,
            "refresh_token": decrypt_secret(connection.encrypted_refresh_token, settings.master_key),
            "grant_type": "refresh_token",
        }).encode(),
        headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read())["access_token"]
    except (HTTPError, KeyError, TimeoutError, URLError, OSError):
        raise HTTPException(502, "Gmail-Zugriff ist abgelaufen. Bitte Gmail erneut verbinden.") from None


@router.get("/projects/{project_id}/gmail/status")
def gmail_status(project_id: uuid.UUID, db: Session = Depends(get_db), actor: Actor = Depends(require_actor)):
    require_project_access(db, actor, project_id, {"project_lead", "company_admin"})
    project = db.get(Project, project_id)
    connection = db.scalar(select(GmailConnection).where(GmailConnection.tenant_id == project.tenant_id, GmailConnection.user_id == actor.user.id))
    return {"configured": bool(settings.gmail_client_id and settings.gmail_client_secret), "connected": bool(connection), "email": connection.email if connection else None}


@router.get("/projects/{project_id}/gmail/connect")
def gmail_connect(project_id: uuid.UUID, db: Session = Depends(get_db), actor: Actor = Depends(require_actor)):
    require_project_access(db, actor, project_id, {"project_lead", "company_admin"})
    if not settings.gmail_client_id or not settings.gmail_client_secret:
        raise HTTPException(503, "Gmail-OAuth ist nicht konfiguriert. Client-ID und Client-Secret fehlen.")
    project = db.get(Project, project_id)
    query = urlencode({
        "client_id": settings.gmail_client_id, "redirect_uri": settings.gmail_redirect_uri,
        "response_type": "code", "scope": SCOPES, "access_type": "offline",
        "prompt": "consent", "include_granted_scopes": "true",
        "state": _state_token(project.id, project.tenant_id, actor.user.id),
    })
    return RedirectResponse("https://accounts.google.com/o/oauth2/v2/auth?" + query, status_code=302)


@router.get("/gmail/callback")
def gmail_callback(code: str, state: str, db: Session = Depends(get_db)):
    claims = _read_state(state)
    user_id, tenant_id, project_id = uuid.UUID(claims["user"]), uuid.UUID(claims["tenant"]), uuid.UUID(claims["project"])
    project = db.get(Project, project_id)
    user = db.get(User, user_id)
    has_admin = db.scalar(select(TenantMembership.id).where(TenantMembership.tenant_id == tenant_id, TenantMembership.user_id == user_id, TenantMembership.role == "company_admin"))
    has_lead = db.scalar(select(ProjectMembership.id).where(ProjectMembership.project_id == project_id, ProjectMembership.user_id == user_id, ProjectMembership.role == "project_lead"))
    if not project or project.tenant_id != tenant_id or not user or not user.active or not (has_admin or has_lead):
        raise HTTPException(403, "Gmail-Verknüpfung ist für dieses Projekt nicht mehr zulässig")
    tokens = _exchange_code(code)
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        raise HTTPException(400, "Google hat kein Refresh-Token geliefert. Bitte Verbindung erneut starten.")
    access_token = tokens.get("access_token")
    profile = _request_json("https://gmail.googleapis.com/gmail/v1/users/me/profile", token=access_token)
    connection = db.scalar(select(GmailConnection).where(GmailConnection.tenant_id == tenant_id, GmailConnection.user_id == user_id))
    encrypted = encrypt_secret(refresh_token, settings.master_key)
    if connection:
        connection.email = profile["emailAddress"]
        connection.encrypted_refresh_token = encrypted
    else:
        db.add(GmailConnection(tenant_id=tenant_id, user_id=user_id, email=profile["emailAddress"], encrypted_refresh_token=encrypted, created_by=user_id))
    db.commit()
    return RedirectResponse(f"/projects/{project_id}/offers?gmail=connected", status_code=303)


def _decode_body(payload: dict) -> str:
    plain = []
    html = []
    def visit(part: dict) -> None:
        data = (part.get("body") or {}).get("data")
        mime = part.get("mimeType")
        if data and mime in {"text/plain", "text/html"}:
            decoded = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", "replace")
            (plain if mime == "text/plain" else html).append(decoded)
        for child in part.get("parts") or []:
            visit(child)
    visit(payload)
    if plain:
        return "\n".join(plain).strip()[:20000]
    class StripHTML(HTMLParser):
        def __init__(self):
            super().__init__(); self.parts = []
        def handle_data(self, data):
            if data.strip(): self.parts.append(data.strip())
    parser = StripHTML(); parser.feed(" ".join(html))
    return "\n".join(parser.parts).strip()[:20000]


def sync_offer_replies(db: Session, version: OfferVersion) -> None:
    links = db.execute(select(GmailOfferThread, GmailConnection).join(GmailConnection).where(GmailOfferThread.offer_version_id == version.id)).all()
    for link, connection in links:
        token = _access_token(connection)
        thread = _request_json(f"https://gmail.googleapis.com/gmail/v1/users/me/threads/{link.gmail_thread_id}?format=full", token=token)
        for message in thread.get("messages", []):
            provider_id = f"gmail:{message.get('id')}"
            if not message.get("id") or db.scalar(select(OfferResponse.id).where(OfferResponse.provider_message_id == provider_id)):
                continue
            headers = {x.get("name", "").lower(): x.get("value", "") for x in (message.get("payload") or {}).get("headers", [])}
            sender_name, sender_email = parseaddr(headers.get("from", ""))
            if not sender_email or sender_email.lower() == connection.email.lower():
                continue
            body = _decode_body(message.get("payload") or {})
            if not body:
                continue
            stamp = datetime.fromtimestamp(int(message.get("internalDate", "0")) / 1000, tz=timezone.utc)
            db.add(OfferResponse(
                offer_version_id=version.id, author_name=sender_name or sender_email,
                author_email=sender_email, channel="email", provider_message_id=provider_id,
                body=body, created_at=stamp, updated_at=stamp,
            ))
            db.flush()
    db.commit()


@router.post("/offer-versions/{version_id}/gmail-drafts")
def create_gmail_draft(version_id: uuid.UUID, payload: EmailDraftRequest, db: Session = Depends(get_db), actor: Actor = Depends(require_csrf)):
    version = db.get(OfferVersion, version_id)
    if not version:
        raise HTTPException(404, "Angebotsversion nicht gefunden")
    offer = db.get(Offer, version.offer_id)
    require_project_access(db, actor, offer.project_id, {"project_lead", "company_admin"})
    if version.status not in {"freigegeben", "versendet", "angenommen"}:
        raise HTTPException(409, "Nur ein freigegebenes Angebot kann per Gmail vorbereitet werden")
    recipient = parseaddr(payload.to.strip())[1]
    if not recipient or "@" not in recipient:
        raise HTTPException(422, "Bitte eine gültige Empfängeradresse angeben")
    connection = db.scalar(select(GmailConnection).where(GmailConnection.tenant_id == offer.tenant_id, GmailConnection.user_id == actor.user.id))
    if not connection:
        raise HTTPException(409, "Bitte zuerst das eigene Gmail-Konto mit diesem Projekt verbinden")
    artifact = db.scalar(select(PublishedArtifact).where(
        PublishedArtifact.offer_version_id == version.id,
        PublishedArtifact.kind == "docx", PublishedArtifact.immutable.is_(True),
    ).order_by(PublishedArtifact.created_at.desc()))
    file = db.get(FileArtifact, artifact.file_artifact_id) if artifact else None
    if not file:
        raise HTTPException(409, "Zum freigegebenen Angebot gibt es kein DOCX als Anlage")
    message = EmailMessage()
    message["To"] = recipient
    message["From"] = connection.email
    message["Subject"] = payload.subject.strip()
    message.set_content(payload.body.strip())
    message.add_attachment(storage.read(file), maintype="application", subtype="vnd.openxmlformats-officedocument.wordprocessingml.document", filename=file.filename)
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode().rstrip("=")
    result = _request_json("https://gmail.googleapis.com/gmail/v1/users/me/drafts", method="POST", data={"message": {"raw": raw}}, token=_access_token(connection))
    thread_id = (result.get("message") or {}).get("threadId")
    if thread_id:
        existing = db.scalar(select(GmailOfferThread.id).where(GmailOfferThread.offer_version_id == version.id, GmailOfferThread.gmail_thread_id == thread_id))
        if not existing:
            db.add(GmailOfferThread(offer_version_id=version.id, gmail_connection_id=connection.id, gmail_thread_id=thread_id, recipient_email=recipient, created_by=actor.user.id))
            db.commit()
    return {"draft_id": result.get("id"), "thread_id": thread_id, "gmail_url": f"https://mail.google.com/mail/u/0/#drafts/{result.get('id')}"}
