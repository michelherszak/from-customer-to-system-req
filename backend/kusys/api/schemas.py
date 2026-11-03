from __future__ import annotations

from datetime import date
from decimal import Decimal
from pydantic import BaseModel, Field


class DemoProjectResponse(BaseModel):
    project: str
    requirements: int
    work_packages: int
    project_start: date
    project_finish: date
    critical_path: list[str]
    net_eur: Decimal
    gross_eur: Decimal
    margin_eur: Decimal


class ImpactResponse(BaseModel):
    requirement_id: str
    dependent_requirements: list[str]
    affected_work_packages: list[str]
    hours_delta: int
    net_delta_eur: Decimal
    finish_delta_days: int


class AnalyzeTextRequest(BaseModel):
    text: str = Field(min_length=1, max_length=60000)
