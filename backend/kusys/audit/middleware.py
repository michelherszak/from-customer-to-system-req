from __future__ import annotations

import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from kusys.auth.service import COOKIE_NAME
from kusys.common.security import token_hash
from kusys.persistence.database import SessionLocal
from kusys.persistence.models import AuditEvent, UserSession

class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        correlation_id=request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
        response=await call_next(request)
        response.headers["X-Correlation-ID"]=correlation_id
        if request.method not in {"GET","HEAD","OPTIONS"}:
            try:
                with SessionLocal() as db:
                    user_id=None
                    raw=request.cookies.get(COOKIE_NAME)
                    if raw:
                        s=db.query(UserSession).filter(UserSession.token_hash==token_hash(raw)).first()
                        if s:user_id=s.user_id
                    # Never record request body, customer text, secrets, or tokens.
                    db.add(AuditEvent(user_id=user_id,action=f"http.{request.method.lower()}",entity_type="route",entity_id=request.url.path[:64],correlation_id=correlation_id,metadata_json={"status":response.status_code}))
                    db.commit()
            except Exception:
                pass
        return response
