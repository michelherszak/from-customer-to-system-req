from __future__ import annotations

import uuid
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from kusys.auth.service import Actor, require_actor, require_csrf, require_project_access
from kusys.common.locking import bump_version, check_expected_version
from kusys.persistence.database import get_db
from kusys.persistence.models import Holiday, Project, WorkCalendar
from kusys.services.calculation import ensure_calendar

router = APIRouter(tags=["calendar"])

class CalendarUpdate(BaseModel):
    expected_version: int
    weekdays: list[int] | None = None
    hours_per_day: int | None = None

class HolidayCreate(BaseModel):
    day: date
    name: str
    kind: str = "holiday"


def serialize_calendar(c: WorkCalendar, holidays: list[Holiday]) -> dict:
    return {
        "id": str(c.id), "name": c.name, "weekdays": c.weekdays,
        "hours_per_day": c.hours_per_day, "lock_version": c.lock_version,
        "holidays": [{"id": str(x.id), "day": x.day.isoformat(), "name": x.name, "kind": x.kind} for x in holidays],
    }


@router.get("/projects/{project_id}/calendar")
def get_calendar(project_id: uuid.UUID, db: Session = Depends(get_db), actor: Actor = Depends(require_actor)):
    require_project_access(db, actor, project_id)
    p = db.get(Project, project_id)
    c = ensure_calendar(db, p, actor.user.id); db.commit()
    holidays = list(db.scalars(select(Holiday).where(Holiday.calendar_id == c.id).order_by(Holiday.day)))
    return serialize_calendar(c, holidays)


@router.patch("/projects/{project_id}/calendar")
def update_calendar(project_id: uuid.UUID, payload: CalendarUpdate, db: Session = Depends(get_db), actor: Actor = Depends(require_csrf)):
    require_project_access(db, actor, project_id, {"project_lead", "company_admin"})
    p = db.get(Project, project_id); c = ensure_calendar(db, p, actor.user.id)
    check_expected_version(c, payload.expected_version)
    if payload.weekdays is not None:
        if not payload.weekdays or any(x < 0 or x > 6 for x in payload.weekdays):
            raise HTTPException(422, "Wochentage müssen Werte 0-6 enthalten")
        c.weekdays = sorted(set(payload.weekdays))
    if payload.hours_per_day is not None:
        if not 1 <= payload.hours_per_day <= 24:
            raise HTTPException(422, "Stunden pro Arbeitstag müssen zwischen 1 und 24 liegen")
        c.hours_per_day = payload.hours_per_day
    bump_version(c); db.commit(); db.refresh(c)
    holidays = list(db.scalars(select(Holiday).where(Holiday.calendar_id == c.id).order_by(Holiday.day)))
    return serialize_calendar(c, holidays)


@router.post("/projects/{project_id}/calendar/holidays")
def add_holiday(project_id: uuid.UUID, payload: HolidayCreate, db: Session = Depends(get_db), actor: Actor = Depends(require_csrf)):
    require_project_access(db, actor, project_id, {"project_lead", "company_admin"})
    p = db.get(Project, project_id); c = ensure_calendar(db, p, actor.user.id)
    if db.scalar(select(Holiday).where(Holiday.calendar_id == c.id, Holiday.day == payload.day)):
        raise HTTPException(409, "Für dieses Datum existiert bereits ein Kalendereintrag")
    h = Holiday(calendar_id=c.id, day=payload.day, name=payload.name, kind=payload.kind, created_by=actor.user.id)
    db.add(h); db.commit(); db.refresh(h)
    return {"id": str(h.id), "day": h.day.isoformat(), "name": h.name, "kind": h.kind}


@router.delete("/calendar/holidays/{holiday_id}")
def delete_holiday(holiday_id: uuid.UUID, db: Session = Depends(get_db), actor: Actor = Depends(require_csrf)):
    h = db.get(Holiday, holiday_id)
    if not h:
        raise HTTPException(404, "Kalendereintrag nicht gefunden")
    c = db.get(WorkCalendar, h.calendar_id)
    if not c or not c.project_id:
        raise HTTPException(422, "Firmenkalender kann hier nicht geändert werden")
    require_project_access(db, actor, c.project_id, {"project_lead", "company_admin"})
    db.delete(h); db.commit(); return {"status": "deleted"}
