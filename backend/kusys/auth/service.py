from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from kusys.common.config import get_settings
from kusys.common.security import (
    constant_time_equal, hash_password, random_token, token_hash, utcnow, validate_username, verify_password,
)
from kusys.persistence.database import get_db
from kusys.persistence.models import (
    LoginEvent, PlatformAccessGrant, ProjectMembership, TenantMembership, User, UserSession,
)

COOKIE_NAME = "kusys_session"
settings = get_settings()


@dataclass(frozen=True, slots=True)
class Actor:
    user: User
    session: UserSession




def _aware_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

def _ip_hash(request: Request) -> str:
    ip = request.client.host if request.client else "unknown"
    return hashlib.sha256(ip.encode()).hexdigest()


def create_user(db: Session, username: str, display_name: str, password: str, email: str | None = None, is_platform_admin: bool = False) -> User:
    normalized = validate_username(username)
    if db.scalar(select(User).where(func.lower(User.username) == normalized)):
        raise ValueError("Benutzername existiert bereits")
    user = User(
        username=normalized,
        display_name=display_name,
        email=email,
        password_hash=hash_password(password),
        is_platform_admin=is_platform_admin,
    )
    db.add(user)
    db.flush()
    return user


def _is_locked(db: Session, username: str, ip_hash: str) -> bool:
    cutoff = utcnow() - timedelta(seconds=settings.base_lock_seconds)
    failures = db.scalar(
        select(func.count(LoginEvent.id)).where(
            LoginEvent.occurred_at >= cutoff,
            LoginEvent.success.is_(False),
            (func.lower(LoginEvent.username) == username.lower()) | (LoginEvent.ip_hash == ip_hash),
        )
    ) or 0
    return failures >= settings.failed_login_threshold


def login(db: Session, request: Request, response: Response, username: str, password: str) -> dict:
    normalized = username.strip().lower()
    ip_hash = _ip_hash(request)
    if _is_locked(db, normalized, ip_hash):
        raise HTTPException(status_code=429, detail="Zu viele fehlgeschlagene Anmeldeversuche. Bitte später erneut versuchen.")
    user = db.scalar(select(User).where(func.lower(User.username) == normalized, User.deleted_at.is_(None)))
    valid = bool(user and user.active and verify_password(password, user.password_hash))
    db.add(LoginEvent(username=normalized, ip_hash=ip_hash, success=valid))
    if not valid:
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Ungültige Zugangsdaten")
    raw_token = random_token(32)
    csrf = random_token(24)
    now = utcnow()
    sess = UserSession(
        user_id=user.id,
        token_hash=token_hash(raw_token),
        csrf_token=csrf,
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(hours=settings.session_absolute_hours),
        ip_hash=ip_hash,
    )
    db.add(sess)
    db.commit()
    response.set_cookie(
        COOKIE_NAME,
        raw_token,
        httponly=True,
        samesite="lax",
        secure=settings.secure_cookies,
        max_age=settings.session_absolute_hours * 3600,
        path="/",
    )
    return {"user": serialize_user(user), "csrf_token": csrf}


def logout(db: Session, response: Response, actor: Actor) -> None:
    actor.session.revoked_at = utcnow()
    db.commit()
    response.delete_cookie(COOKIE_NAME, path="/")


def serialize_user(user: User) -> dict:
    return {
        "id": str(user.id),
        "username": user.username,
        "display_name": user.display_name,
        "email": user.email,
        "is_platform_admin": user.is_platform_admin,
    }


def optional_actor(request: Request, db: Session = Depends(get_db)) -> Actor | None:
    raw = request.cookies.get(COOKIE_NAME)
    if not raw:
        return None
    sess = db.scalar(select(UserSession).where(UserSession.token_hash == token_hash(raw)))
    if not sess or sess.revoked_at is not None:
        return None
    now = utcnow()
    idle_limit = now - timedelta(minutes=settings.session_idle_minutes)
    if _aware_utc(sess.expires_at) <= now or _aware_utc(sess.last_seen_at) < idle_limit:
        sess.revoked_at = now
        db.commit()
        return None
    user = db.get(User, sess.user_id)
    if not user or not user.active or user.deleted_at is not None:
        return None
    sess.last_seen_at = now
    db.commit()
    return Actor(user=user, session=sess)


def require_actor(actor: Actor | None = Depends(optional_actor)) -> Actor:
    if actor is None:
        raise HTTPException(status_code=401, detail="Anmeldung erforderlich")
    return actor


def require_csrf(request: Request, actor: Actor = Depends(require_actor)) -> Actor:
    if not settings.csrf_required or request.method in {"GET", "HEAD", "OPTIONS"}:
        return actor
    supplied = request.headers.get("X-CSRF-Token", "")
    if not supplied or not constant_time_equal(supplied, actor.session.csrf_token):
        raise HTTPException(status_code=403, detail="CSRF-Token fehlt oder ist ungültig")
    return actor


def tenant_roles(db: Session, user_id: uuid.UUID) -> dict[uuid.UUID, str]:
    return {m.tenant_id: m.role for m in db.scalars(select(TenantMembership).where(TenantMembership.user_id == user_id))}


def has_tenant_access(db: Session, actor: Actor, tenant_id: uuid.UUID, roles: set[str] | None = None) -> bool:
    membership = db.scalar(select(TenantMembership).where(TenantMembership.user_id == actor.user.id, TenantMembership.tenant_id == tenant_id))
    if membership and (roles is None or membership.role in roles):
        return True
    if actor.user.is_platform_admin:
        now = utcnow()
        grant = db.scalar(select(PlatformAccessGrant).where(
            PlatformAccessGrant.tenant_id == tenant_id,
            PlatformAccessGrant.requester_id == actor.user.id,
            PlatformAccessGrant.status == "active",
            PlatformAccessGrant.valid_from <= now,
            PlatformAccessGrant.valid_until > now,
        ))
        if grant and roles is None:
            return True
    return False


def require_tenant_access(db: Session, actor: Actor, tenant_id: uuid.UUID, roles: set[str] | None = None) -> None:
    if not has_tenant_access(db, actor, tenant_id, roles):
        raise HTTPException(status_code=403, detail="Kein Zugriff auf diese Firma")


def require_project_access(db: Session, actor: Actor, project_id: uuid.UUID, roles: set[str] | None = None):
    # Standard project endpoints are internal-only. Customer users must use explicitly published portal endpoints.
    effective_roles = roles if roles is not None else {"project_lead", "project_member", "company_admin"}
    # Rights are resolved before caller queries the protected domain object by returning membership only.
    pm = db.scalar(select(ProjectMembership).where(ProjectMembership.project_id == project_id, ProjectMembership.user_id == actor.user.id))
    if pm and pm.role in effective_roles:
        return pm
    # company admins may access all projects in their tenant; resolve tenant via membership+project in a single join
    from kusys.persistence.models import Project
    row = db.execute(
        select(Project.tenant_id, TenantMembership.role)
        .join(TenantMembership, TenantMembership.tenant_id == Project.tenant_id)
        .where(Project.id == project_id, TenantMembership.user_id == actor.user.id)
    ).first()
    if row and row.role == "company_admin" and "company_admin" in effective_roles:
        return row
    raise HTTPException(status_code=403, detail="Kein Projektzugriff")
