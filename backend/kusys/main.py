from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from kusys.common.config import get_settings
from kusys.persistence.database import SessionLocal
from kusys.audit.middleware import AuditMiddleware
from kusys.auth.api import router as auth_router
from kusys.auth.admin_api import router as user_router
from kusys.tenancy.api import router as tenancy_router
from kusys.customers.api import router as customer_router
from kusys.projects.api import router as project_router
from kusys.documents.api import router as document_router
from kusys.review.api import router as review_router
from kusys.analysis.api import router as analysis_router
from kusys.requirements.api import router as requirement_router
from kusys.planning.api import router as planning_router
from kusys.baselines.api import router as baseline_router
from kusys.offers.api import router as offer_router
from kusys.templates.api import router as template_router
from kusys.jobs.api import router as job_router
from kusys.artifacts.api import router as artifact_router
from kusys.presence.api import router as presence_router
from kusys.audit.api import router as audit_router
from kusys.portal.api import router as portal_router
from kusys.commercial.api import router as commercial_router
from kusys.calendars.api import router as calendar_router
from kusys.ai_config.api import router as ai_config_router

settings=get_settings()
app=FastAPI(title="KuSys API",version=settings.app_version,description="Kundendokument → Prüfschritt → Anforderungen → Arbeitspakete → Terminplan → Angebot")
app.add_middleware(AuditMiddleware)
app.add_middleware(CORSMiddleware,allow_origins=[settings.frontend_origin],allow_credentials=True,allow_methods=["*"],allow_headers=["*"])

for router in [auth_router,user_router,tenancy_router,customer_router,project_router,document_router,review_router,analysis_router,requirement_router,planning_router,baseline_router,offer_router,template_router,job_router,artifact_router,presence_router,audit_router,portal_router,commercial_router,calendar_router,ai_config_router]:
    app.include_router(router,prefix="/api/v1")

@app.get("/api/v1/health")
def health():
    status="healthy";db_status="ok"
    try:
        with SessionLocal() as db: db.execute(text("SELECT 1"))
    except Exception as exc:
        status="unhealthy";db_status=type(exc).__name__
    return {"status":status,"service":"kusys","version":settings.app_version,"database":db_status,"optional":{"external_ai":"not_required","external_ocr":"not_required"}}
