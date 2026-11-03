from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint, Uuid
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class IdMixin:
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)


class LockMixin:
    lock_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    delete_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class Tenant(Base, IdMixin, TimestampMixin, LockMixin):
    __tablename__ = "tenant"
    name: Mapped[str] = mapped_column(String(200), unique=True)
    address: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str] = mapped_column(String(2), default="DE")
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(80))
    contact_name: Mapped[str | None] = mapped_column(String(200))
    vat_id: Mapped[str | None] = mapped_column(String(80))
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    language: Mapped[str] = mapped_column(String(8), default="de")
    timezone: Mapped[str] = mapped_column(String(80), default="Europe/Berlin")


class User(Base, IdMixin, TimestampMixin, LockMixin, SoftDeleteMixin):
    __tablename__ = "user_account"
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    password_hash: Mapped[str] = mapped_column(Text)
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class TenantMembership(Base, IdMixin, TimestampMixin):
    __tablename__ = "tenant_membership"
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user_account.id"), index=True)
    role: Mapped[str] = mapped_column(String(32))
    __table_args__ = (UniqueConstraint("tenant_id", "user_id"),)


class PlatformAccessRequest(Base, IdMixin, TimestampMixin):
    __tablename__ = "platform_access_request"
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    requester_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user_account.id"))
    reason: Mapped[str] = mapped_column(Text)
    requested_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), default="pending")


class PlatformAccessGrant(Base, IdMixin, TimestampMixin):
    __tablename__ = "platform_access_grant"
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    requester_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user_account.id"))
    approver_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user_account.id"))
    reason: Mapped[str] = mapped_column(Text)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), default="active")


class Customer(Base, IdMixin, TimestampMixin, LockMixin, SoftDeleteMixin):
    __tablename__ = "customer"
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    customer_number: Mapped[str] = mapped_column(String(80))
    company_name: Mapped[str] = mapped_column(String(240))
    address: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str] = mapped_column(String(2), default="DE")
    contact_name: Mapped[str | None] = mapped_column(String(200))
    department: Mapped[str | None] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(80))
    __table_args__ = (UniqueConstraint("tenant_id", "customer_number"),)


class Project(Base, IdMixin, TimestampMixin, LockMixin, SoftDeleteMixin):
    __tablename__ = "project"
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    project_number: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(240))
    short_description: Mapped[str | None] = mapped_column(Text)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("customer.id"), nullable=True)
    customer_contact: Mapped[str | None] = mapped_column(String(200))
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("user_account.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active")
    confidential: Mapped[bool] = mapped_column(Boolean, default=False)
    document_language: Mapped[str] = mapped_column(String(8), default="de")
    planned_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    __table_args__ = (UniqueConstraint("tenant_id", "project_number"),)


class ProjectMembership(Base, IdMixin, TimestampMixin):
    __tablename__ = "project_membership"
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user_account.id"), index=True)
    role: Mapped[str] = mapped_column(String(32))
    __table_args__ = (UniqueConstraint("project_id", "user_id"),)


class Document(Base, IdMixin, TimestampMixin, LockMixin, SoftDeleteMixin):
    __tablename__ = "document"
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project.id"), index=True)
    name: Mapped[str] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(80), default="customer_document")


class DocumentVersion(Base, IdMixin, TimestampMixin):
    __tablename__ = "document_version"
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    filename: Mapped[str] = mapped_column(String(300))
    mime_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="uploaded")
    page_count: Mapped[int | None] = mapped_column(Integer)
    language: Mapped[str | None] = mapped_column(String(8))
    extraction_meta: Mapped[dict | None] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint("document_id", "version"),)


class ExtractedBlock(Base, IdMixin, TimestampMixin):
    __tablename__ = "extracted_block"
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    document_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document_version.id"), index=True)
    page_number: Mapped[int | None] = mapped_column(Integer)
    block_index: Mapped[int] = mapped_column(Integer)
    block_type: Mapped[str] = mapped_column(String(32), default="paragraph")
    heading_path: Mapped[str | None] = mapped_column(Text)
    source_text: Mapped[str] = mapped_column(Text)
    normalized_text: Mapped[str] = mapped_column(Text)
    coordinates: Mapped[dict | None] = mapped_column(JSON)
    table_meta: Mapped[dict | None] = mapped_column(JSON)
    source_checksum: Mapped[str] = mapped_column(String(64))
    text_source: Mapped[str] = mapped_column(String(32), default="native")
    quality_status: Mapped[str] = mapped_column(String(32), default="good")


class ReviewRevision(Base, IdMixin, TimestampMixin, LockMixin):
    __tablename__ = "review_revision"
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project.id"), index=True)
    revision_no: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("user_account.id"))
    source_selection: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (UniqueConstraint("project_id", "revision_no"),)


class Section(Base, IdMixin, TimestampMixin, LockMixin, SoftDeleteMixin):
    __tablename__ = "section"
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    review_revision_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("review_revision.id"), index=True)
    extracted_block_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("extracted_block.id"))
    order_index: Mapped[int] = mapped_column(Integer)
    section_type: Mapped[str] = mapped_column(String(32), default="paragraph")
    heading_level: Mapped[int | None] = mapped_column(Integer)
    source_text: Mapped[str] = mapped_column(Text)
    normalized_text: Mapped[str] = mapped_column(Text)
    edited_text: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(32), default="context")
    category_source: Mapped[str] = mapped_column(String(32), default="automatic")
    excluded: Mapped[bool] = mapped_column(Boolean, default=False)
    manual: Mapped[bool] = mapped_column(Boolean, default=False)
    review_note: Mapped[str | None] = mapped_column(Text)


class SectionRevision(Base, IdMixin, TimestampMixin):
    __tablename__ = "section_revision"
    section_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("section.id"), index=True)
    revision_no: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict] = mapped_column(JSON)


class AnalysisRun(Base, IdMixin, TimestampMixin):
    __tablename__ = "analysis_run"
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project.id"), index=True)
    review_revision_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("review_revision.id"))
    provider: Mapped[str] = mapped_column(String(80), default="rule-based")
    model_id: Mapped[str] = mapped_column(String(160), default="rule-based-v1")
    schema_version: Mapped[str] = mapped_column(String(40), default="1")
    status: Mapped[str] = mapped_column(String(32), default="queued")
    stale: Mapped[bool] = mapped_column(Boolean, default=False)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result_json: Mapped[dict | None] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(80))


class AnalysisStep(Base, IdMixin, TimestampMixin):
    __tablename__ = "analysis_step"
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("analysis_run.id"), index=True)
    step_name: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(32))
    result_json: Mapped[dict | None] = mapped_column(JSON)


class Requirement(Base, IdMixin, TimestampMixin, LockMixin, SoftDeleteMixin):
    __tablename__ = "requirement"
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project.id"), index=True)
    key: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(300))
    text: Mapped[str] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(16), default="soll")
    origin: Mapped[str] = mapped_column(String(32), default="analysis")
    business_revision: Mapped[int] = mapped_column(Integer, default=1)
    budget_eur: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    max_price_eur: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    budget_source: Mapped[str | None] = mapped_column(String(32))
    source_refs: Mapped[list] = mapped_column(JSON, default=list)
    replacement_status: Mapped[str | None] = mapped_column(String(80))
    __table_args__ = (UniqueConstraint("project_id", "key"),)


class RequirementRevision(Base, IdMixin, TimestampMixin):
    __tablename__ = "requirement_revision"
    requirement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("requirement.id"), index=True)
    revision_no: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint("requirement_id", "revision_no"),)


class RequirementRelation(Base, IdMixin, TimestampMixin):
    __tablename__ = "requirement_relation"
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project.id"), index=True)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("requirement.id"), index=True)
    target_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("requirement.id"), index=True)
    relation_type: Mapped[str] = mapped_column(String(32))
    rationale: Mapped[str | None] = mapped_column(Text)
    origin: Mapped[str] = mapped_column(String(32), default="manual")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class RequirementCostAttribution(Base, IdMixin, TimestampMixin):
    __tablename__ = "requirement_cost_attribution"
    offer_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("offer_version.id"), index=True)
    requirement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("requirement.id"), index=True)
    cost_eur: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    sales_eur: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    margin_eur: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    budget_delta_eur: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))


class ClarificationItem(Base, IdMixin, TimestampMixin, LockMixin, SoftDeleteMixin):
    __tablename__ = "clarification_item"
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project.id"), index=True)
    key: Mapped[str] = mapped_column(String(32))
    text: Mapped[str] = mapped_column(Text)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    origin: Mapped[str] = mapped_column(String(32), default="manual")
    status: Mapped[str] = mapped_column(String(64), default="offen")
    requirement_ids: Mapped[list] = mapped_column(JSON, default=list)
    source_refs: Mapped[list] = mapped_column(JSON, default=list)


class ClarificationRevision(Base, IdMixin, TimestampMixin):
    __tablename__ = "clarification_revision"
    clarification_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clarification_item.id"), index=True)
    revision_no: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict] = mapped_column(JSON)


class WorkPackage(Base, IdMixin, TimestampMixin, LockMixin, SoftDeleteMixin):
    __tablename__ = "work_package"
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project.id"), index=True)
    key: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    role_name: Mapped[str] = mapped_column(String(120))
    min_hours: Mapped[int] = mapped_column(Integer, default=0)
    likely_hours: Mapped[int] = mapped_column(Integer, default=0)
    max_hours: Mapped[int] = mapped_column(Integer, default=0)
    plan_hours: Mapped[int] = mapped_column(Integer, default=0)
    max_fte: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("1"))
    planning_priority: Mapped[int] = mapped_column(Integer, default=3)
    phase: Mapped[str] = mapped_column(String(64), default="Realisierung")
    global_package: Mapped[bool] = mapped_column(Boolean, default=False)
    scaling_mode: Mapped[str] = mapped_column(String(40), default="proportional")
    business_revision: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (UniqueConstraint("project_id", "key"),)


class WorkPackageRevision(Base, IdMixin, TimestampMixin):
    __tablename__ = "work_package_revision"
    work_package_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("work_package.id"), index=True)
    revision_no: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict] = mapped_column(JSON)


class WorkPackageRequirement(Base, IdMixin, TimestampMixin):
    __tablename__ = "work_package_requirement"
    work_package_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("work_package.id"), index=True)
    requirement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("requirement.id"), index=True)
    weight: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    __table_args__ = (UniqueConstraint("work_package_id", "requirement_id"),)


class WorkPackageDependency(Base, IdMixin, TimestampMixin):
    __tablename__ = "work_package_dependency"
    predecessor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("work_package.id"), index=True)
    successor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("work_package.id"), index=True)
    relation_type: Mapped[str] = mapped_column(String(16), default="FS")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("predecessor_id", "successor_id"),)


class RateCard(Base, IdMixin, TimestampMixin, LockMixin):
    __tablename__ = "rate_card"
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("project.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    source_rate_card_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class RateCardRole(Base, IdMixin, TimestampMixin, LockMixin):
    __tablename__ = "rate_card_role"
    rate_card_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rate_card.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    aliases: Mapped[list] = mapped_column(JSON, default=list)
    kind: Mapped[str] = mapped_column(String(16), default="internal")
    capacity_fte: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("1"))
    internal_cost_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    purchase_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    markup_percent: Mapped[Decimal | None] = mapped_column(Numeric(7, 2))
    sales_rate: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    __table_args__ = (UniqueConstraint("rate_card_id", "name"),)


class WorkCalendar(Base, IdMixin, TimestampMixin, LockMixin):
    __tablename__ = "work_calendar"
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("project.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(160))
    weekdays: Mapped[list] = mapped_column(JSON, default=lambda: [0, 1, 2, 3, 4])
    hours_per_day: Mapped[int] = mapped_column(Integer, default=8)


class Holiday(Base, IdMixin, TimestampMixin):
    __tablename__ = "holiday"
    calendar_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("work_calendar.id"), index=True)
    day: Mapped[date] = mapped_column(Date)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(32), default="holiday")
    __table_args__ = (UniqueConstraint("calendar_id", "day"),)


class Baseline(Base, IdMixin, TimestampMixin):
    __tablename__ = "baseline"
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    checksum: Mapped[str] = mapped_column(String(64))
    snapshot_json: Mapped[dict] = mapped_column(JSON)


class BaselineRequirement(Base, IdMixin, TimestampMixin):
    __tablename__ = "baseline_requirement"
    baseline_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("baseline.id"), index=True)
    requirement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("requirement.id"))
    requirement_revision: Mapped[int] = mapped_column(Integer)
    snapshot_json: Mapped[dict] = mapped_column(JSON)


class Offer(Base, IdMixin, TimestampMixin, LockMixin, SoftDeleteMixin):
    __tablename__ = "offer"
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project.id"), index=True)
    offer_number: Mapped[str] = mapped_column(String(80))
    variant_name: Mapped[str] = mapped_column(String(160), default="Basis")
    primary_variant: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (UniqueConstraint("tenant_id", "offer_number", "variant_name"),)


class OfferVersion(Base, IdMixin, TimestampMixin, LockMixin):
    __tablename__ = "offer_version"
    offer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("offer.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="Entwurf")
    offer_date: Mapped[date] = mapped_column(Date, default=date.today)
    validity_days: Mapped[int] = mapped_column(Integer, default=30)
    language: Mapped[str] = mapped_column(String(8), default="de")
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    recipient: Mapped[str | None] = mapped_column(String(300), nullable=True)
    customer_reference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    internal_reference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    payment_plan: Mapped[list] = mapped_column(JSON, default=lambda: [{"phase":"Konzept","percent":10},{"phase":"Spezifikation","percent":15},{"phase":"Realisierung","percent":45},{"phase":"Integration","percent":20},{"phase":"Abnahme","percent":10}])
    risk_percent: Mapped[Decimal] = mapped_column(Numeric(7, 2), default=Decimal("0"))
    discount_percent: Mapped[Decimal] = mapped_column(Numeric(7, 2), default=Decimal("0"))
    vat_percent: Mapped[Decimal] = mapped_column(Numeric(7, 2), default=Decimal("19"))
    baseline_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("baseline.id"))
    template_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("document_template_version.id"))
    net_eur: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    gross_eur: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    margin_eur: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("user_account.id"))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("offer_id", "version"),)


class OfferScopeItem(Base, IdMixin, TimestampMixin):
    __tablename__ = "offer_scope_item"
    offer_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("offer_version.id"), index=True)
    requirement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("requirement.id"), index=True)
    included: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("offer_version_id", "requirement_id"),)


class OfferPosition(Base, IdMixin, TimestampMixin):
    __tablename__ = "offer_position"
    offer_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("offer_version.id"), index=True)
    position_no: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    sales_eur: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    customer_visible_hours: Mapped[bool] = mapped_column(Boolean, default=False)


class MaterialItem(Base, IdMixin, TimestampMixin, LockMixin, SoftDeleteMixin):
    __tablename__ = "material_item"
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project.id"), index=True)
    key: Mapped[str] = mapped_column(String(40))
    description: Mapped[str] = mapped_column(Text)
    cost_eur: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    sales_eur: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    requirement_ids: Mapped[list] = mapped_column(JSON, default=list)
    scaling_mode: Mapped[str] = mapped_column(String(40), default="proportional")


class OfferTextBlock(Base, IdMixin, TimestampMixin, LockMixin):
    __tablename__ = "offer_text_block"
    offer_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("offer_version.id"), index=True)
    key: Mapped[str] = mapped_column(String(80))
    content_html: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(8), default="de")


class OfferSnapshot(Base, IdMixin, TimestampMixin):
    __tablename__ = "offer_snapshot"
    offer_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("offer_version.id"), unique=True, index=True)
    snapshot_json: Mapped[dict] = mapped_column(JSON)
    checksum: Mapped[str] = mapped_column(String(64))


class DocumentTemplate(Base, IdMixin, TimestampMixin, LockMixin, SoftDeleteMixin):
    __tablename__ = "document_template"
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(40), default="offer")


class DocumentTemplateVersion(Base, IdMixin, TimestampMixin):
    __tablename__ = "document_template_version"
    template_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document_template.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="Entwurf")
    config_json: Mapped[dict] = mapped_column(JSON, default=dict)
    content_blocks: Mapped[list] = mapped_column(JSON, default=list)
    master_artifact_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    __table_args__ = (UniqueConstraint("template_id", "version"),)


class PublishedArtifact(Base, IdMixin, TimestampMixin):
    __tablename__ = "published_artifact"
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("project.id"))
    offer_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("offer_version.id"))
    file_artifact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("file_artifact.id"))
    kind: Mapped[str] = mapped_column(String(40))
    language: Mapped[str] = mapped_column(String(8), default="de")
    immutable: Mapped[bool] = mapped_column(Boolean, default=True)


class FileArtifact(Base, IdMixin, TimestampMixin):
    __tablename__ = "file_artifact"
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("project.id"), index=True)
    filename: Mapped[str] = mapped_column(String(300))
    mime_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="available")


class AIProviderConfig(Base, IdMixin, TimestampMixin, LockMixin):
    __tablename__ = "ai_provider_config"
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("project.id"))
    provider: Mapped[str] = mapped_column(String(80))
    endpoint: Mapped[str | None] = mapped_column(Text)
    region: Mapped[str | None] = mapped_column(String(80))
    deployment: Mapped[str | None] = mapped_column(String(120))
    allowed_models: Mapped[list] = mapped_column(JSON, default=list)
    encrypted_api_key: Mapped[str | None] = mapped_column(Text)
    confidential_allowed: Mapped[bool] = mapped_column(Boolean, default=False)


class AIModelPrice(Base, IdMixin, TimestampMixin):
    __tablename__ = "ai_model_price"
    provider: Mapped[str] = mapped_column(String(80))
    model_id: Mapped[str] = mapped_column(String(160))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    input_per_million: Mapped[Decimal] = mapped_column(Numeric(14, 6), default=Decimal("0"))
    output_per_million: Mapped[Decimal] = mapped_column(Numeric(14, 6), default=Decimal("0"))
    valid_from: Mapped[date] = mapped_column(Date, default=date.today)


class AIUsageEvent(Base, IdMixin, TimestampMixin):
    __tablename__ = "ai_usage_event"
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("project.id"))
    analysis_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("analysis_run.id"))
    provider: Mapped[str] = mapped_column(String(80))
    model_id: Mapped[str] = mapped_column(String(160))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    provider_cost: Mapped[Decimal] = mapped_column(Numeric(14, 6), default=Decimal("0"))
    provider_currency: Mapped[str] = mapped_column(String(3), default="USD")
    fx_rate_to_eur: Mapped[Decimal] = mapped_column(Numeric(14, 6), default=Decimal("1"))
    cost_eur: Mapped[Decimal] = mapped_column(Numeric(14, 6), default=Decimal("0"))
    status: Mapped[str] = mapped_column(String(32), default="success")


class Job(Base, IdMixin, TimestampMixin):
    __tablename__ = "job"
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tenant.id"), index=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("project.id"), index=True)
    kind: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(32), default="queued")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict | None] = mapped_column(JSON)
    idempotency_key: Mapped[str | None] = mapped_column(String(160), index=True)
    error_code: Mapped[str | None] = mapped_column(String(80))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserSession(Base, IdMixin):
    __tablename__ = "user_session"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user_account.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    csrf_token: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ip_hash: Mapped[str | None] = mapped_column(String(64))


class LoginEvent(Base, IdMixin):
    __tablename__ = "login_event"
    username: Mapped[str] = mapped_column(String(80), index=True)
    ip_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    success: Mapped[bool] = mapped_column(Boolean)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class PresenceSession(Base, IdMixin):
    __tablename__ = "presence_session"
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user_account.id"), index=True)
    area: Mapped[str] = mapped_column(String(120), default="overview")
    last_heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("project_id", "user_id"),)


class AuditEvent(Base, IdMixin):
    __tablename__ = "audit_event"
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tenant.id"), index=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("project.id"), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("user_account.id"))
    action: Mapped[str] = mapped_column(String(120), index=True)
    entity_type: Mapped[str | None] = mapped_column(String(80))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    correlation_id: Mapped[str | None] = mapped_column(String(80), index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
