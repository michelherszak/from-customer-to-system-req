from __future__ import annotations

import uuid
from sqlalchemy.orm import Session
from kusys.persistence.models import AuditEvent


def audit(
    db: Session,
    action: str,
    *,
    tenant_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    correlation_id: str | None = None,
    metadata: dict | None = None,
) -> AuditEvent:
    event = AuditEvent(
        tenant_id=tenant_id,
        project_id=project_id,
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        correlation_id=correlation_id,
        metadata_json=metadata or {},
    )
    db.add(event)
    return event
