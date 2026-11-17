from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path

DB_PATH = Path("/tmp/kusys_pytest_full_flow.db")
STORE_PATH = Path("/tmp/kusys_pytest_artifacts")
os.environ["KUSYS_DATABASE_URL"] = f"sqlite+pysqlite:///{DB_PATH}"
os.environ["KUSYS_STORAGE_PATH"] = str(STORE_PATH)
os.environ["KUSYS_SECURE_COOKIES"] = "false"
os.environ["KUSYS_INLINE_JOBS"] = "true"

from fastapi.testclient import TestClient

from kusys.persistence.database import SessionLocal, engine
from kusys.persistence.models import Base, Document, Project
from kusys.seed import seed_demo

Base.metadata.create_all(engine)
with SessionLocal() as _db:
    seed_demo(_db)

from kusys.main import app


def _login(client: TestClient, username: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "KuSys-Demo-2026"},
    )
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


def test_us_00_ac_01_complete_upload_to_published_offer_flow(monkeypatch):
    client = TestClient(app)
    csrf = _login(client, "max.mustermann")
    headers = {"X-CSRF-Token": csrf}
    projects = client.get("/api/v1/projects")
    assert projects.status_code == 200
    project_id = projects.json()[0]["id"]

    # CSRF is enforced for cookie-authenticated writes.
    denied = client.post(
        f"/api/v1/projects/{project_id}/requirements",
        json={"title": "X", "text": "Das System soll X tun."},
    )
    assert denied.status_code == 403

    fixture = Path(__file__).parents[2] / "fixtures" / "documents" / "Lastenheft_PX2400_v1.docx"
    with fixture.open("rb") as stream:
        upload = client.post(
            f"/api/v1/projects/{project_id}/documents",
            headers=headers,
            files={
                "file": (
                    fixture.name,
                    stream,
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )
    assert upload.status_code == 202, upload.text
    assert upload.json()["version"]["status"] == "ready"
    job = client.get(f"/api/v1/jobs/{upload.json()['job_id']}")
    assert job.status_code == 200 and job.json()["status"] == "succeeded"

    review = client.post(
        f"/api/v1/projects/{project_id}/review/rebuild",
        headers=headers,
        json={"source_selection": {}},
    )
    assert review.status_code == 200, review.text
    review_id = review.json()["id"]
    current = client.get(f"/api/v1/projects/{project_id}/review").json()
    assert any(x["category"] == "requirement" for x in current["sections"])
    approved = client.post(f"/api/v1/review-revisions/{review_id}/approve", headers=headers)
    assert approved.status_code == 200, approved.text

    # The production endpoint must reject a missing real-provider configuration.
    denied_model = client.post(f"/api/v1/projects/{project_id}/analysis-runs", headers=headers)
    assert denied_model.status_code == 422
    from tests.test_engineering_workflow import ScriptedProvider
    from kusys.persistence.models import AIProviderConfig
    from kusys.common.security import encrypt_secret
    from kusys.common.config import get_settings
    class ConfiguredTestProvider(ScriptedProvider):
        def __init__(self, *args):
            super().__init__()
            self.input_tokens = self.output_tokens = 0
        def run_role(self, role, context, schema):
            raw = super().run_role(role, context, schema)
            if role == "systems_engineer":
                raw["system_requirements"][0]["assumptions"] = ["Referenzumgebung fachlich bestätigen"]
            return raw
    monkeypatch.setattr("kusys.analysis.service.CrewAIProvider", ConfiguredTestProvider)
    with SessionLocal() as db:
        project = db.get(Project, uuid.UUID(project_id))
        cfg = AIProviderConfig(tenant_id=project.tenant_id, provider="test-cloud", endpoint="https://example.invalid/v1", allowed_models=["test-model"], encrypted_api_key=encrypt_secret("test-only", get_settings().master_key), confidential_allowed=True)
        db.add(cfg); db.commit(); cfg_id = str(cfg.id)
    analysis = client.post(f"/api/v1/projects/{project_id}/analysis-runs", headers=headers, json={"provider_config_id": cfg_id, "model_id": "test-model"})
    assert analysis.status_code == 202, analysis.text
    run = analysis.json()["analysis_run"]
    assert run["status"] == "succeeded"
    not_confirmed = client.post(f"/api/v1/analysis-runs/{run['id']}/activate", headers=headers)
    assert not_confirmed.status_code == 422
    activated = client.post(f"/api/v1/analysis-runs/{run['id']}/activate", headers=headers, json={"acknowledge_assumptions": True})
    assert activated.status_code == 200, activated.text
    assert activated.json()["requirements"] >= 1

    requirements = client.get(f"/api/v1/projects/{project_id}/requirements").json()
    work_packages = client.get(f"/api/v1/projects/{project_id}/work-packages").json()
    assert requirements and work_packages

    conflict = client.patch(
        f"/api/v1/requirements/{requirements[0]['id']}",
        headers=headers,
        json={"expected_version": 999, "budget_eur": 18000},
    )
    assert conflict.status_code == 409

    updated = client.patch(
        f"/api/v1/requirements/{requirements[0]['id']}",
        headers=headers,
        json={"expected_version": requirements[0]["lock_version"], "budget_eur": 18000},
    )
    assert updated.status_code == 200, updated.text
    impact = client.get(f"/api/v1/requirements/{requirements[0]['id']}/impact")
    assert impact.status_code == 200, impact.text
    assert "hours_delta" in impact.json() and "net_delta_eur" in impact.json()

    schedule = client.get(f"/api/v1/projects/{project_id}/schedule")
    assert schedule.status_code == 200, schedule.text
    assert schedule.json()["packages"]
    assert schedule.json()["project_finish"]

    clarification = client.post(
        f"/api/v1/projects/{project_id}/clarifications",
        headers=headers,
        json={"text": "Bitte Wartungsfenster bestätigen.", "requirement_ids": [requirements[0]["id"]]},
    )
    assert clarification.status_code == 200, clarification.text
    clarification_id = clarification.json()["id"]

    created_offer = client.post(
        f"/api/v1/projects/{project_id}/offers",
        headers=headers,
        json={
            "offer_number": "ANG-2026-0001",
            "variant_name": "Basis",
            "primary_variant": True,
            "language": "de",
        },
    )
    assert created_offer.status_code == 200, created_offer.text
    version_id = created_offer.json()["version"]["id"]
    preview = client.get(f"/api/v1/offer-versions/{version_id}/preview")
    assert preview.status_code == 200, preview.text
    assert float(preview.json()["pricing"]["net_eur"]) > 0

    submitted = client.post(
        f"/api/v1/offer-versions/{version_id}/status",
        headers=headers,
        json={"target_status": "zur Freigabe"},
    )
    assert submitted.status_code == 200, submitted.text
    own_approval = client.post(
        f"/api/v1/offer-versions/{version_id}/status",
        headers=headers,
        json={"target_status": "freigegeben"},
    )
    assert own_approval.status_code == 409

    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 200
    csrf_approver = _login(client, "lea.pruefer")
    approver_headers = {"X-CSRF-Token": csrf_approver}
    approved_offer = client.post(
        f"/api/v1/offer-versions/{version_id}/status",
        headers=approver_headers,
        json={"target_status": "freigegeben"},
    )
    assert approved_offer.status_code == 200, approved_offer.text

    docx = client.post(
        f"/api/v1/offer-versions/{version_id}/export?format=docx",
        headers=approver_headers,
    )
    xlsx = client.post(
        f"/api/v1/offer-versions/{version_id}/export?format=xlsx&internal=true",
        headers=approver_headers,
    )
    assert docx.status_code == 200 and xlsx.status_code == 200
    docx_id = docx.json()["artifact_id"]
    xlsx_id = xlsx.json()["artifact_id"]
    assert client.get(f"/api/v1/artifacts/{docx_id}").content[:2] == b"PK"
    assert client.get(f"/api/v1/artifacts/{xlsx_id}").content[:2] == b"PK"

    # Approved versions are immutable.
    immutable = client.patch(
        f"/api/v1/offer-versions/{version_id}",
        headers=approver_headers,
        json={"expected_version": approved_offer.json()["lock_version"], "discount_percent": 5},
    )
    assert immutable.status_code == 409

    assert client.post("/api/v1/auth/logout", headers=approver_headers).status_code == 200
    customer_csrf = _login(client, "kunde.nordstern")
    portal = client.get(f"/api/v1/portal/projects/{project_id}")
    assert portal.status_code == 200, portal.text
    assert any(x["artifact_id"] == docx_id for x in portal.json()["published_artifacts"])
    assert client.get(f"/api/v1/artifacts/{docx_id}").status_code == 200
    answer = client.post(
        f"/api/v1/portal/clarifications/{clarification_id}/answer",
        headers={"X-CSRF-Token": customer_csrf},
        json={"answer": "Wartungsfenster sonntags 06:00–08:00 Uhr."},
    )
    assert answer.status_code == 200, answer.text
    assert answer.json()["status"] == "beantwortet – interne Prüfung ausstehend"

    assert client.post(
        "/api/v1/auth/logout", headers={"X-CSRF-Token": customer_csrf}
    ).status_code == 200
    _login(client, "platform.admin")
    assert client.get("/api/v1/projects").json() == []

def test_us_00_ac_02_extended_v1_editing_surfaces():
    client = TestClient(app)
    csrf = _login(client, "max.mustermann")
    headers = {"X-CSRF-Token": csrf}
    project_id = client.get("/api/v1/projects").json()[0]["id"]

    # Project calendar and non-working days are editable and feed the planning engine.
    calendar = client.get(f"/api/v1/projects/{project_id}/calendar")
    assert calendar.status_code == 200
    cal = calendar.json()
    changed = client.patch(
        f"/api/v1/projects/{project_id}/calendar",
        headers=headers,
        json={"expected_version": cal["lock_version"], "hours_per_day": 7, "weekdays": [0,1,2,3,4]},
    )
    assert changed.status_code == 200
    holiday = client.post(
        f"/api/v1/projects/{project_id}/calendar/holidays",
        headers=headers,
        json={"day": "2026-10-03", "name": "Testfeiertag", "kind": "holiday"},
    )
    assert holiday.status_code in {200, 409}

    # Materials can be attributed to requirements and are included in pricing.
    reqs = client.get(f"/api/v1/projects/{project_id}/requirements").json()
    if not reqs:
        created = client.post(
            f"/api/v1/projects/{project_id}/requirements", headers=headers,
            json={"title":"Testanforderung","text":"Das System soll getestet werden.","budget_eur":1000},
        )
        assert created.status_code == 200
        reqs = [created.json()]
    material = client.post(
        f"/api/v1/projects/{project_id}/materials",
        headers=headers,
        json={"description":"Gateway","cost_eur":100,"sales_eur":180,"requirement_ids":[reqs[0]["id"]],"scaling_mode":"proportional"},
    )
    assert material.status_code == 200, material.text
    assert client.get(f"/api/v1/projects/{project_id}/materials").json()

    # Review supports split/merge semantics after a rebuild.
    rebuild = client.post(f"/api/v1/projects/{project_id}/review/rebuild", headers=headers, json={"source_selection":{}})
    if rebuild.status_code == 200:
        review = client.get(f"/api/v1/projects/{project_id}/review").json()
        sections = [x for x in review["sections"] if not x["deleted"]]
        if sections:
            s = sections[0]
            split = client.post(
                f"/api/v1/review-revisions/{review['review']['id']}/sections/{s['id']}/split",
                headers=headers,
                json={"expected_version":s["lock_version"],"parts":["Teil A","Teil B"]},
            )
            assert split.status_code == 200, split.text

    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 200

    # Company admins can configure encrypted AI provider profiles without exposing keys.
    admin_csrf = _login(client, "sophie.schneider")
    admin_headers = {"X-CSRF-Token": admin_csrf}
    tenant_id = client.get("/api/v1/tenants").json()[0]["id"]
    providers = client.get(f"/api/v1/tenants/{tenant_id}/ai-providers")
    assert providers.status_code == 200
    if not providers.json():
        created_provider = client.post(
            "/api/v1/ai-providers", headers=admin_headers,
            json={"tenant_id":tenant_id,"provider":"example","endpoint":"https://example.invalid","allowed_models":["model-1"],"confidential_allowed":False,"api_key":"test-secret"},
        )
        assert created_provider.status_code == 200, created_provider.text
        assert created_provider.json()["has_api_key"] is True
        assert "api_key" not in created_provider.json()


def test_only_project_leads_can_delete_documents():
    client = TestClient(app)
    lead_csrf = _login(client, "max.mustermann")
    project_id = client.get("/api/v1/projects").json()[0]["id"]
    with SessionLocal() as db:
        project = db.get(Project, uuid.UUID(project_id))
        document = Document(tenant_id=project.tenant_id, project_id=project.id, name="Berechtigungstest")
        db.add(document)
        db.commit()
        document_id = str(document.id)

    endpoint = f"/api/v1/documents/{document_id}?reason=Berechtigungstest"
    for username in ("tom.mitglied", "sophie.schneider", "kunde.nordstern"):
        csrf = _login(client, username)
        denied = client.delete(endpoint, headers={"X-CSRF-Token": csrf})
        assert denied.status_code == 403, (username, denied.text)
        with SessionLocal() as db:
            assert db.get(Document, uuid.UUID(document_id)).deleted_at is None

    lead_csrf = _login(client, "max.mustermann")
    deleted = client.delete(endpoint, headers={"X-CSRF-Token": lead_csrf})
    assert deleted.status_code == 200, deleted.text
    with SessionLocal() as db:
        assert db.get(Document, uuid.UUID(document_id)).deleted_at is not None
    assert document_id not in {
        item["id"] for item in client.get(f"/api/v1/projects/{project_id}/documents").json()
    }


def test_engineering_history_export_and_budget_are_persisted():
    client = TestClient(app)
    _login(client, "max.mustermann")
    project_id = client.get("/api/v1/projects").json()[0]["id"]
    runs = client.get(f"/api/v1/projects/{project_id}/analysis-runs").json()
    run = next(x for x in runs if x.get("result", {}).get("quality"))
    result = run["result"]
    assert result["quality"]["offline"] is False
    assert result["quality"]["acknowledgement"]["actor_id"]
    assert result["system_requirements"][0]["parent_keys"]
    assert result["activation_mapping"]["requirements"]
    scenario = result["estimate_summary"]["scenarios"]["likely"]
    assert scenario["project_finish"]
    assert float(scenario["labor_cost_eur"]) > 0
    steps = client.get(f"/api/v1/analysis-runs/{run['id']}/steps")
    assert steps.status_code == 200
    assert any(x["name"].startswith("review_round:") for x in steps.json())
    diagnostic = client.get(f"/api/v1/analysis-runs/{run['id']}/diagnostics")
    assert diagnostic.status_code == 200
    events = [e for step in diagnostic.json()["steps"] for e in step["events"]]
    assert events and all(e["started_at"] and e["finished_at"] for e in events)
    assert all("outputs" not in step for step in diagnostic.json()["steps"])
    assert "api_key" not in diagnostic.text
    document = client.get(f"/api/v1/analysis-runs/{run['id']}/documentation")
    assert document.status_code == 200
    assert "Review-Historie" in document.text
    assert "verification_criterion" in document.text
    assert "rate_snapshot" in document.text
    assert "attachment" in document.headers["content-disposition"]
    _login(client, "kunde.nordstern")
    assert client.get(f"/api/v1/analysis-runs/{run['id']}/documentation").status_code == 403
    assert client.get(f"/api/v1/analysis-runs/{run['id']}/diagnostics").status_code == 403


def test_blocker_cannot_be_overridden_with_assumption_acknowledgement():
    from copy import deepcopy
    from sqlalchemy import select
    from kusys.persistence.models import AnalysisRun
    client = TestClient(app)
    csrf = _login(client, "max.mustermann")
    project_id = client.get("/api/v1/projects").json()[0]["id"]
    with SessionLocal() as db:
        previous = db.scalar(select(AnalysisRun).where(AnalysisRun.project_id == uuid.UUID(project_id), AnalysisRun.status == "activated"))
        result = deepcopy(previous.result_json)
        result["quality"]["status"] = "blocked"
        blocked = AnalysisRun(tenant_id=previous.tenant_id, project_id=previous.project_id, review_revision_id=previous.review_revision_id, provider="test", model_id="test", schema_version="engineering-v2", status="succeeded", result_json=result)
        db.add(blocked); db.commit(); blocked_id = str(blocked.id)
    response = client.post(f"/api/v1/analysis-runs/{blocked_id}/activate", headers={"X-CSRF-Token": csrf}, json={"acknowledge_assumptions": True})
    assert response.status_code == 422
    assert "Review blockiert" in response.text


def test_document_preparation_preview_preserves_review_and_manual_corrections():
    from sqlalchemy import select
    from kusys.persistence.models import Job, Section
    client = TestClient(app)
    csrf = _login(client, "max.mustermann")
    headers = {"X-CSRF-Token": csrf}
    project_id = client.get("/api/v1/projects").json()[0]["id"]
    before = client.get(f"/api/v1/projects/{project_id}/review").json()
    original_id = before["review"]["id"]
    source = next(x for x in before["sections"] if x["category"] == "requirement")
    changed = client.patch(f"/api/v1/review-revisions/{original_id}/sections/{source['id']}", headers=headers, json={"expected_version": source["lock_version"], "edited_text": "Manuell korrigierter Kundenabschnitt.", "category": "context"})
    assert changed.status_code == 200
    documents = client.get(f"/api/v1/projects/{project_id}/documents").json()
    version_id = next(v["id"] for doc in documents for v in doc["versions"] if v["status"] == "ready")
    preparation = client.post(f"/api/v1/projects/{project_id}/document-preparations", headers=headers, json={"document_version_id": version_id})
    assert preparation.status_code == 202, preparation.text
    job_id = preparation.json()["job_id"]
    result = client.get(f"/api/v1/jobs/{job_id}").json()["result"]
    assert result["metrics"]["source_coverage"] == "100%"
    after_preview = client.get(f"/api/v1/projects/{project_id}/review").json()
    assert after_preview["review"]["id"] == original_id
    assert next(x for x in after_preview["sections"] if x["id"] == source["id"])["edited_text"] == "Manuell korrigierter Kundenabschnitt."
    applied = client.post(f"/api/v1/projects/{project_id}/review/rebuild", headers=headers, json={"preparation_job_id": job_id, "expected_review_id": original_id})
    assert applied.status_code == 200, applied.text
    assert applied.json()["id"] != original_id
    assert applied.json()["status"] == "draft"
    new = client.get(f"/api/v1/projects/{project_id}/review").json()
    assert any(x["edited_text"] == "Manuell korrigierter Kundenabschnitt." and x["category"] == "context" for x in new["sections"])
    # A stale screen cannot silently create another revision.
    stale = client.post(f"/api/v1/projects/{project_id}/review/rebuild", headers=headers, json={"preparation_job_id": job_id, "expected_review_id": original_id})
    assert stale.status_code == 422
    with SessionLocal() as db:
        assert db.get(Section, uuid.UUID(source["id"])).edited_text == "Manuell korrigierter Kundenabschnitt."


def test_model_selection_only_needs_catalog_and_key():
    from kusys.persistence.models import AIProviderConfig
    from kusys.common.security import decrypt_secret
    from kusys.common.config import get_settings
    client=TestClient(app)
    csrf=_login(client,"max.mustermann")
    tenant_id=client.get("/api/v1/tenants").json()[0]["id"]
    catalog=client.get("/api/v1/ai-model-catalog")
    assert catalog.status_code==200 and len(catalog.json())>=3
    assert all("endpoint" not in x for x in catalog.json())
    denied=client.post("/api/v1/ai-model-selection",headers={"X-CSRF-Token":csrf},json={"tenant_id":tenant_id,"catalog_id":"openai/gpt-5.4-mini","api_key":"test-key-only"})
    assert denied.status_code==403
    csrf=_login(client,"sophie.schneider")
    headers={"X-CSRF-Token":csrf}
    saved=client.post("/api/v1/ai-model-selection",headers=headers,json={"tenant_id":tenant_id,"catalog_id":"openai/gpt-5.4-mini","api_key":"test-key-only"})
    assert saved.status_code==200,saved.text
    assert saved.json()["endpoint"]=="https://api.openai.com/v1"
    assert saved.json()["engine"]=="crewai"
    assert "test-key-only" not in saved.text
    with SessionLocal() as db:
        cfg=db.get(AIProviderConfig,uuid.UUID(saved.json()["id"]))
        encrypted=cfg.encrypted_api_key
        assert encrypted!="test-key-only"
        assert decrypt_secret(encrypted,get_settings().master_key)=="test-key-only"
    changed=client.post("/api/v1/ai-model-selection",headers=headers,json={"tenant_id":tenant_id,"catalog_id":"openai/gpt-5.4","expected_version":saved.json()["lock_version"]})
    assert changed.status_code==200,changed.text
    assert set(changed.json()["allowed_models"])=={"gpt-5.4-mini","gpt-5.4"}
    with SessionLocal() as db:
        assert db.get(AIProviderConfig,uuid.UUID(saved.json()["id"])).encrypted_api_key==encrypted
    stale=client.post("/api/v1/ai-model-selection",headers=headers,json={"tenant_id":tenant_id,"catalog_id":"openai/gpt-5.4","expected_version":saved.json()["lock_version"],"api_key":"replacement"})
    assert stale.status_code==409
    unknown=client.post("/api/v1/ai-model-selection",headers=headers,json={"tenant_id":tenant_id,"catalog_id":"invented/model","api_key":"no"})
    assert unknown.status_code==422


def test_company_admin_and_project_lead_can_delete_projects():
    from kusys.persistence.models import ProjectMembership, User
    from sqlalchemy import select
    client=TestClient(app)
    for allowed in ("max.mustermann", "sophie.schneider"):
        csrf=_login(client,"max.mustermann")
        tenant_id=client.get("/api/v1/projects").json()[0]["tenant_id"]
        with SessionLocal() as db:
            project=Project(tenant_id=uuid.UUID(tenant_id),project_number=f"DELETE-{uuid.uuid4()}",name="Isolierter Löschtest")
            db.add(project);db.flush()
            for name,role in (("max.mustermann","project_lead"),("tom.mitglied","project_member")):
                user=db.scalar(select(User).where(User.username==name))
                db.add(ProjectMembership(project_id=project.id,user_id=user.id,role=role))
            db.commit();project_id=str(project.id)
        endpoint=f"/api/v1/projects/{project_id}?reason=Berechtigungstest"
        for denied in ("tom.mitglied","kunde.nordstern","platform.admin"):
            csrf=_login(client,denied)
            assert client.delete(endpoint,headers={"X-CSRF-Token":csrf}).status_code==403
        csrf=_login(client,allowed)
        assert client.delete(endpoint).status_code==403
        assert client.delete(endpoint,headers={"X-CSRF-Token":csrf}).status_code==200
        assert project_id not in {p["id"] for p in client.get("/api/v1/projects").json()}
        assert client.get(f"/api/v1/projects/{project_id}").status_code==404
        with SessionLocal() as db:
            project=db.get(Project,uuid.UUID(project_id))
            assert project.deleted_at and project.deleted_by and project.delete_reason=="Berechtigungstest"


def test_project_creation_is_available_to_company_admin_and_project_leads_only():
    from sqlalchemy import select
    from kusys.persistence.models import ProjectMembership, User
    client=TestClient(app)
    _login(client,"max.mustermann")
    tenant_id=client.get("/api/v1/projects").json()[0]["tenant_id"]
    for name in ("tom.mitglied","kunde.nordstern","platform.admin"):
        csrf=_login(client,name)
        assert client.get("/api/v1/project-creation-options").json()==[]
        response=client.post("/api/v1/projects",headers={"X-CSRF-Token":csrf},json={"tenant_id":tenant_id,"project_number":f"DENIED-{uuid.uuid4()}","name":"Denied"})
        assert response.status_code==403,(name,response.text)
    for name in ("max.mustermann","lea.pruefer","sophie.schneider"):
        csrf=_login(client,name)
        options=client.get("/api/v1/project-creation-options")
        assert options.status_code==200 and tenant_id in {t["id"] for t in options.json()}
        payload={"tenant_id":tenant_id,"project_number":f"CREATE-{uuid.uuid4()}","name":" Neues Projekt ","short_description":"Beschreibung"}
        assert client.post("/api/v1/projects",json=payload).status_code==403
        assert client.post("/api/v1/projects",headers={"X-CSRF-Token":csrf},json={**payload,"tenant_id":str(uuid.uuid4())}).status_code==403
        assert client.post("/api/v1/projects",headers={"X-CSRF-Token":csrf},json={**payload,"name":"   "}).status_code==422
        response=client.post("/api/v1/projects",headers={"X-CSRF-Token":csrf},json=payload)
        assert response.status_code==200,response.text
        project=response.json()
        assert project["name"]=="Neues Projekt"
        assert client.get(f"/api/v1/projects/{project['id']}").status_code==200
        assert any(r["project_id"]==project["id"] and r["role"]=="project_lead" for r in client.get("/api/v1/auth/me").json()["project_roles"])
        duplicate=client.post("/api/v1/projects",headers={"X-CSRF-Token":csrf},json=payload)
        assert duplicate.status_code==409
        with SessionLocal() as db:
            user=db.scalar(select(User).where(User.username==name))
            row=db.scalar(select(ProjectMembership).where(ProjectMembership.project_id==uuid.UUID(project["id"]),ProjectMembership.user_id==user.id))
            assert row.role=="project_lead"


def test_analysis_resume_and_fresh_start_use_persisted_checkpoints(monkeypatch):
    from sqlalchemy import select
    from kusys.persistence.models import AnalysisRun, ReviewRevision, Section, AIProviderConfig, AnalysisStep
    from kusys.common.security import encrypt_secret
    from kusys.common.config import get_settings
    from tests.test_engineering_workflow import ScriptedProvider
    calls=[]
    failure={"enabled":True}
    class Provider(ScriptedProvider):
        def __init__(self,*args):
            super().__init__();self.provider_id=args[0];self.model_id=args[3]
            self.input_tokens=self.output_tokens=0
        def run_role(self,role,context,schema):
            calls.append(role)
            if role=="work_planner" and failure["enabled"]:
                raise ValueError("Synthetic interruption")
            return super().run_role(role,context,schema)
    monkeypatch.setattr("kusys.analysis.service.CrewAIProvider",Provider)
    client=TestClient(app);csrf=_login(client,"sophie.schneider");headers={"X-CSRF-Token":csrf}
    tenant_id=client.get("/api/v1/project-creation-options").json()[0]["id"]
    created=client.post("/api/v1/projects",headers=headers,json={"tenant_id":tenant_id,"project_number":f"RESUME-{uuid.uuid4()}","name":"Checkpoint integration"}).json()
    project_id=created["id"]
    with SessionLocal() as db:
        review=ReviewRevision(project_id=uuid.UUID(project_id),tenant_id=uuid.UUID(tenant_id),revision_no=1,status="approved")
        db.add(review);db.flush()
        text="Das System muss Daten nachweisbar speichern."
        db.add(Section(tenant_id=uuid.UUID(tenant_id),review_revision_id=review.id,order_index=1,source_text=text,normalized_text=text,edited_text=text,category="requirement"))
        cfg=AIProviderConfig(tenant_id=uuid.UUID(tenant_id),provider="test-cloud",endpoint="https://example.invalid",allowed_models=["test-model"],encrypted_api_key=encrypt_secret("test",get_settings().master_key))
        db.add(cfg);db.commit();cfg_id=str(cfg.id)
    failed=client.post(f"/api/v1/projects/{project_id}/analysis-runs",headers=headers,json={"provider_config_id":cfg_id,"model_id":"test-model"})
    assert failed.status_code==422
    run=client.get(f"/api/v1/projects/{project_id}/analysis-runs").json()[0]
    assert run["status"]=="failed"
    failure["enabled"]=False;calls.clear()
    assert client.post(f"/api/v1/analysis-runs/{run['id']}/resume").status_code==403
    resumed=client.post(f"/api/v1/analysis-runs/{run['id']}/resume",headers=headers)
    assert resumed.status_code==202,resumed.text
    assert resumed.json()["analysis_run"]["id"]!=run["id"]
    assert calls[0]=="work_planner"
    diagnostic=client.get(f"/api/v1/analysis-runs/{resumed.json()['analysis_run']['id']}/diagnostics").json()
    assert any(e["status"]=="cached" for s in diagnostic["steps"] for e in s["events"])
    assert client.get(f"/api/v1/projects/{project_id}/analysis-runs").json()[-1]["status"]=="failed"
    calls.clear()
    fresh=client.post(f"/api/v1/analysis-runs/{run['id']}/restart",headers=headers)
    assert fresh.status_code==202,fresh.text
    assert calls[0]=="requirements_engineer"
    # A changed approved source revision must not silently resume the old one.
    with SessionLocal() as db:
        db.add(ReviewRevision(project_id=uuid.UUID(project_id),tenant_id=uuid.UUID(tenant_id),revision_no=2,status="approved"));db.commit()
    assert client.post(f"/api/v1/analysis-runs/{run['id']}/resume",headers=headers).status_code==422
    _login(client,"kunde.nordstern")
    csrf=client.get("/api/v1/auth/me").json()["csrf_token"]
    assert client.post(f"/api/v1/analysis-runs/{run['id']}/resume",headers={"X-CSRF-Token":csrf}).status_code==403


def test_company_agent_settings_are_authorized_versioned_and_used_by_new_runs(monkeypatch):
    from sqlalchemy import select
    from kusys.persistence.models import Tenant,ReviewRevision,Section,AIProviderConfig,Job
    from kusys.common.security import encrypt_secret
    from kusys.common.config import get_settings
    from tests.test_engineering_workflow import ScriptedProvider
    client=TestClient(app);csrf=_login(client,"sophie.schneider");headers={"X-CSRF-Token":csrf}
    tenant_id=client.get("/api/v1/tenants").json()[0]["id"]
    endpoint=f"/api/v1/tenants/{tenant_id}/agent-settings"
    original=client.get(endpoint).json()
    project=client.post("/api/v1/projects",headers=headers,json={"tenant_id":tenant_id,"project_number":f"SETTINGS-{uuid.uuid4()}","name":"Agent settings test"}).json()
    with SessionLocal() as db:
        cfg=AIProviderConfig(tenant_id=uuid.UUID(tenant_id),provider="settings-test",endpoint="https://example.invalid",allowed_models=["settings-model"],encrypted_api_key=encrypt_secret("never-return-this-key",get_settings().master_key))
        db.add(cfg);db.flush();cfg_id=str(cfg.id)
        review=ReviewRevision(tenant_id=uuid.UUID(tenant_id),project_id=uuid.UUID(project["id"]),revision_no=1,status="approved")
        db.add(review);db.flush();text="Das System muss Daten speichern."
        db.add(Section(tenant_id=uuid.UUID(tenant_id),review_revision_id=review.id,order_index=1,category="requirement",source_text=text,normalized_text=text,edited_text=text));db.commit()
    payload={"expected_version":original["lock_version"],"max_rounds":1,"default_provider_config_id":cfg_id,"default_model_id":"settings-model","instructions":{"systems_engineer":"Use SI units."}}
    assert client.put(endpoint,json=payload).status_code==403
    saved=client.put(endpoint,headers=headers,json=payload)
    assert saved.status_code==200,saved.text
    assert saved.json()["settings"]["instructions"]==payload["instructions"]
    assert "never-return-this-key" not in saved.text
    assert len(saved.json()["agents"])==5
    assert client.put(endpoint,headers=headers,json=payload).status_code==409
    version=saved.json()["lock_version"]
    assert client.put(endpoint,headers=headers,json={**payload,"expected_version":version,"instructions":{"unknown":"x"}}).status_code==422
    assert client.put(endpoint,headers=headers,json={**payload,"expected_version":version,"max_rounds":4}).status_code==422
    for username in ("max.mustermann","tom.mitglied","platform.admin"):
        token=_login(client,username)
        assert client.get(endpoint).status_code==403
        assert client.put(endpoint,headers={"X-CSRF-Token":token},json={**payload,"expected_version":version}).status_code==403
    csrf=_login(client,"sophie.schneider");headers={"X-CSRF-Token":csrf}
    observed=[]
    class Provider(ScriptedProvider):
        def __init__(self,*args):
            super().__init__();self.provider_id=args[0];self.model_id=args[3];self.input_tokens=self.output_tokens=0
        def run_role(self,role,context,schema):
            observed.append(dict(self.instructions))
            return super().run_role(role,context,schema)
    monkeypatch.setattr("kusys.analysis.service.CrewAIProvider",Provider)
    result=client.post(f"/api/v1/projects/{project['id']}/analysis-runs",headers=headers,json={})
    assert result.status_code==202,result.text
    run=result.json()["analysis_run"]
    assert run["model_id"]=="settings-model"
    assert run["result"]["quality"]["max_rounds"]==1
    assert all(x==payload["instructions"] for x in observed)
    options=client.get(f"/api/v1/projects/{project['id']}/analysis-options").json()
    assert options[0]["id"]==cfg_id and options[0]["is_default"]
    with SessionLocal() as db:
        job=db.scalar(select(Job).where(Job.kind=="analysis",Job.payload["analysis_run_id"].as_string()==run["id"]))
        assert job.payload["agent_settings"]["max_rounds"]==1
    restore=client.put(endpoint,headers=headers,json={**original["settings"],"expected_version":version})
    assert restore.status_code==200,restore.text


def test_planning_to_offer_flow_requires_active_packages_and_calculates_exports():
    from sqlalchemy import select
    from kusys.persistence.models import WorkPackage, Offer
    client=TestClient(app);csrf=_login(client,"sophie.schneider");headers={"X-CSRF-Token":csrf}
    tenant_id=client.get("/api/v1/tenants").json()[0]["id"]
    empty=client.post("/api/v1/projects",headers=headers,json={"tenant_id":tenant_id,"project_number":f"EMPTY-OFFER-{uuid.uuid4()}","name":"Empty offer test"}).json()
    denied=client.post(f"/api/v1/projects/{empty['id']}/offers",headers=headers,json={})
    assert denied.status_code==422
    assert client.get(f"/api/v1/projects/{empty['id']}/offers").json()==[]
    with SessionLocal() as db:
        project_id=str(db.scalar(select(WorkPackage.project_id).where(WorkPackage.deleted_at.is_(None)).limit(1)))
    current=client.get(f"/api/v1/projects/{project_id}").json()
    changed=client.patch(f"/api/v1/projects/{project_id}",headers=headers,json={"expected_version":current["lock_version"],"planned_start":"2030-01-07"})
    assert changed.status_code==200
    packages=client.get(f"/api/v1/projects/{project_id}/work-packages").json()
    wp=packages[0]
    updated=client.patch(f"/api/v1/work-packages/{wp['id']}",headers=headers,json={"expected_version":wp["lock_version"],"plan_hours":wp["plan_hours"]+8})
    assert updated.status_code==200,updated.text
    schedule=client.get(f"/api/v1/projects/{project_id}/schedule")
    assert schedule.status_code==200,schedule.text
    assert schedule.json()["project_start"]=="2030-01-07"
    assert {p["id"] for p in schedule.json()["packages"]}=={p["id"] for p in packages}
    offers=[]
    for _ in range(2):
        response=client.post(f"/api/v1/projects/{project_id}/offers",headers=headers,json={})
        assert response.status_code==200,response.text
        offers.append(response.json())
    rows=client.get(f"/api/v1/projects/{project_id}/offers").json()
    number1=next(row["offer_number"] for row in rows if row["id"]==offers[0]["offer_id"])
    number2=next(row["offer_number"] for row in rows if row["id"]==offers[1]["offer_id"])
    assert number1!=number2 and number1.startswith("ANG-")
    duplicate=client.post(f"/api/v1/projects/{project_id}/offers",headers=headers,json={"offer_number":number1})
    assert duplicate.status_code==409
    with SessionLocal() as db:
        assert db.get(Offer,uuid.UUID(offers[1]["offer_id"])).primary_variant
    version=offers[1]["version"]["id"]
    preview=client.get(f"/api/v1/offer-versions/{version}/preview")
    assert preview.status_code==200,preview.text
    data=preview.json()
    assert data["work_packages"] and float(data["pricing"]["net_eur"])>0
    assert data["schedule"]["project_start"]=="2030-01-07"
    for extension in ("docx","xlsx"):
        export=client.post(f"/api/v1/offer-versions/{version}/export?format={extension}",headers=headers)
        assert export.status_code==200,export.text
    rate=next(row for row in client.get(f"/api/v1/projects/{project_id}/rate-card").json()["roles"] if row["name"]==wp["role_name"])
    assert client.patch(f"/api/v1/rate-card-roles/{rate['id']}",headers=headers,json={"expected_version":rate["lock_version"],"capacity_fte":-1}).status_code==422
    zero=client.patch(f"/api/v1/rate-card-roles/{rate['id']}",headers=headers,json={"expected_version":rate["lock_version"],"capacity_fte":0})
    assert zero.status_code==200
    invalid=client.get(f"/api/v1/offer-versions/{version}/preview")
    assert invalid.status_code==422 and "Angebotskalkulation" in invalid.text
    assert client.patch(f"/api/v1/rate-card-roles/{rate['id']}",headers=headers,json={"expected_version":zero.json()["lock_version"],"capacity_fte":rate["capacity_fte"]}).status_code==200
    assert client.get(f"/api/v1/offer-versions/{version}/preview").status_code==200
    submitted=client.post(f"/api/v1/offer-versions/{version}/status",headers=headers,json={"target_status":"zur Freigabe"})
    assert submitted.status_code==200,submitted.text
    latest=client.get(f"/api/v1/projects/{project_id}/offers").json()
    assert next(v for row in latest for v in row["versions"] if v["id"]==version)["status"]=="zur Freigabe"


def test_blocked_completed_review_can_resume_without_activating(monkeypatch):
    from sqlalchemy import select
    from types import SimpleNamespace
    from kusys.persistence.models import AnalysisRun,AIProviderConfig,Job,ReviewRevision
    from kusys.common.config import get_settings
    client=TestClient(app);csrf=_login(client,"sophie.schneider");headers={"X-CSRF-Token":csrf}
    tenant_id=client.get("/api/v1/tenants").json()[0]["id"]
    project=client.post("/api/v1/projects",headers=headers,json={"tenant_id":tenant_id,"project_number":f"BLOCKED-{uuid.uuid4()}","name":"Blocked resume test"}).json()
    with SessionLocal() as db:
        cfg=next(c for c in db.scalars(select(AIProviderConfig).where(AIProviderConfig.tenant_id==uuid.UUID(tenant_id))) if c.endpoint and c.encrypted_api_key and c.allowed_models)
        review=ReviewRevision(tenant_id=uuid.UUID(tenant_id),project_id=uuid.UUID(project["id"]),revision_no=1,status="approved")
        db.add(review);db.flush()
        source=AnalysisRun(tenant_id=uuid.UUID(tenant_id),project_id=uuid.UUID(project["id"]),review_revision_id=review.id,provider=cfg.provider,model_id=cfg.allowed_models[0],status="succeeded",schema_version="engineering-v2",result_json={"quality":{"status":"blocked","max_rounds":1}})
        db.add(source);db.flush()
        db.add(Job(tenant_id=uuid.UUID(tenant_id),project_id=uuid.UUID(project["id"]),kind="analysis",status="succeeded",payload={"analysis_run_id":str(source.id),"provider_config_id":str(cfg.id),"model_id":source.model_id}));db.commit();source_id=str(source.id)
    monkeypatch.setattr(get_settings(),"inline_jobs",False)
    dispatched=[]
    monkeypatch.setattr("kusys.jobs.tasks.analysis_task",SimpleNamespace(delay=lambda *args:dispatched.append(args)))
    response=client.post(f"/api/v1/analysis-runs/{source_id}/resume",headers=headers)
    assert response.status_code==202,response.text
    assert dispatched and response.json()["analysis_run"]["id"]!=source_id
    assert client.post(f"/api/v1/analysis-runs/{source_id}/activate",headers=headers).status_code==422
    assert client.get(f"/api/v1/projects/{project['id']}/work-packages").json()==[]


def test_project_list_matches_access_and_members_need_explicit_assignment():
    from sqlalchemy import select
    from kusys.persistence.models import User
    client=TestClient(app);csrf=_login(client,"sophie.schneider");headers={"X-CSRF-Token":csrf}
    tenant_id=client.get("/api/v1/tenants").json()[0]["id"]
    created=client.post("/api/v1/projects",headers=headers,json={"tenant_id":tenant_id,"project_number":f"VISIBILITY-{uuid.uuid4()}","name":"Membership visibility test"})
    assert created.status_code==200,created.text
    project_id=created.json()["id"]
    assert project_id in {p["id"] for p in client.get("/api/v1/projects").json()}
    for username in ("tom.mitglied","max.mustermann","kunde.nordstern"):
        _login(client,username)
        assert project_id not in {p["id"] for p in client.get("/api/v1/projects").json()}
        assert client.get(f"/api/v1/projects/{project_id}").status_code==403
    csrf=_login(client,"sophie.schneider");headers={"X-CSRF-Token":csrf}
    with SessionLocal() as db:
        tom=db.scalar(select(User).where(User.username=="tom.mitglied"));tom_id=str(tom.id)
        customer=db.scalar(select(User).where(User.username=="kunde.nordstern"));customer_id=str(customer.id)
    assert client.post(f"/api/v1/projects/{project_id}/members",headers=headers,json={"user_id":tom_id,"role":"project_member"}).status_code==200
    assert client.post(f"/api/v1/projects/{project_id}/members",headers=headers,json={"user_id":customer_id,"role":"customer"}).status_code==200
    token=_login(client,"tom.mitglied")
    assert project_id in {p["id"] for p in client.get("/api/v1/projects").json()}
    assert client.get(f"/api/v1/projects/{project_id}").status_code==200
    assert client.delete(f"/api/v1/projects/{project_id}?reason=denied",headers={"X-CSRF-Token":token}).status_code==403
    _login(client,"kunde.nordstern")
    assert project_id not in {p["id"] for p in client.get("/api/v1/projects").json()}
    assert client.get(f"/api/v1/projects/{project_id}").status_code==403


def test_project_creator_can_manage_company_members_and_customer_access():
    from sqlalchemy import select
    from kusys.persistence.models import Tenant,TenantMembership,User
    client=TestClient(app);token=_login(client,"max.mustermann");headers={"X-CSRF-Token":token}
    tenant_id=client.get("/api/v1/project-creation-options").json()[0]["id"]
    project=client.post("/api/v1/projects",headers=headers,json={"tenant_id":tenant_id,"project_number":f"TEAM-{uuid.uuid4()}","name":"Project team test"}).json()
    project_id=project["id"]
    base=f"/api/v1/projects/{project_id}"
    candidates=client.get(base+"/member-candidates")
    assert candidates.status_code==200,candidates.text
    people={person["username"]:person for person in candidates.json()}
    assert {"lea.pruefer","tom.mitglied","kunde.nordstern"}.issubset(people)
    assert "sophie.schneider" not in people
    assert people["kunde.nordstern"]["default_role"]=="customer"
    assert "password_hash" not in candidates.text
    with SessionLocal() as db:
        foreign_tenant=Tenant(name=f"Foreign-{uuid.uuid4()}");db.add(foreign_tenant);db.flush()
        foreign=User(username=f"foreign-{uuid.uuid4()}",display_name="Foreign user",password_hash="not-a-login")
        inactive=User(username=f"inactive-{uuid.uuid4()}",display_name="Inactive user",password_hash="not-a-login",active=False)
        db.add_all([foreign,inactive]);db.flush()
        db.add(TenantMembership(tenant_id=foreign_tenant.id,user_id=foreign.id,role="project_member"))
        db.add(TenantMembership(tenant_id=uuid.UUID(tenant_id),user_id=inactive.id,role="project_member"));db.commit()
        forbidden=[str(foreign.id),str(inactive.id),str(uuid.uuid4())]
    available={person["id"] for person in client.get(base+"/member-candidates").json()}
    for user_id in forbidden:
        assert user_id not in available
        assert client.post(base+"/members",headers=headers,json={"user_id":user_id,"role":"project_member"}).status_code==422
    tom=people["tom.mitglied"];lea=people["lea.pruefer"];anna=people["kunde.nordstern"]
    assert client.post(base+"/members",json={"user_id":tom["id"],"role":"project_member"}).status_code==403
    assert client.post(base+"/members",headers=headers,json={"user_id":anna["id"],"role":"project_member"}).status_code==422
    assert client.post(base+"/members",headers=headers,json={"user_id":tom["id"],"role":"customer"}).status_code==422
    for person,role in ((tom,"project_member"),(lea,"project_lead"),(anna,"customer")):
        added=client.post(base+"/members",headers=headers,json={"user_id":person["id"],"role":role})
        assert added.status_code==200,added.text
        assert added.json()["display_name"]==person["display_name"]
    assert client.post(base+"/members",headers=headers,json={"user_id":tom["id"],"role":"project_member"}).status_code==200
    assert client.post(base+"/members",headers=headers,json={"user_id":tom["id"],"role":"project_lead"}).status_code==409
    assert sum(member["user_id"]==tom["id"] for member in client.get(base+"/members").json())==1
    assert tom["id"] not in {person["id"] for person in client.get(base+"/member-candidates").json()}
    token=_login(client,"tom.mitglied")
    assert client.get(base).status_code==200
    assert project_id in {row["id"] for row in client.get("/api/v1/projects").json()}
    assert client.get(base+"/member-candidates").status_code==403
    assert client.delete(base+f"/members/{lea['id']}",headers={"X-CSRF-Token":token}).status_code==403
    _login(client,"kunde.nordstern")
    assert client.get(base).status_code==403
    assert client.get(f"/api/v1/portal/projects/{project_id}").status_code==200
    _login(client,"sophie.schneider")
    assert client.get(base).status_code==200
    assert not any(row["project_id"]==project_id for row in client.get("/api/v1/auth/me").json()["project_roles"])
    token=_login(client,"max.mustermann");max_id=client.get("/api/v1/auth/me").json()["user"]["id"]
    assert client.delete(base+f"/members/{max_id}",headers={"X-CSRF-Token":token}).status_code==200
    assert client.get(base).status_code==403
    token=_login(client,"lea.pruefer")
    assert client.delete(base+f"/members/{lea['id']}",headers={"X-CSRF-Token":token}).status_code==409
    assert client.delete(base+f"/members/{tom['id']}",headers={"X-CSRF-Token":token}).status_code==200
    _login(client,"tom.mitglied")
    assert client.get(base).status_code==403
    assert project_id not in {row["id"] for row in client.get("/api/v1/projects").json()}


def test_project_lead_can_answer_review_blockers_and_request_audited_recheck(monkeypatch):
    from sqlalchemy import select
    from kusys.persistence.models import Tenant,ReviewRevision,Section,AIProviderConfig,AnalysisRun,AnalysisStep,User
    from kusys.common.config import get_settings
    from kusys.common.security import encrypt_secret
    from tests.test_engineering_workflow import ScriptedProvider
    answer='Jede Aufnahme gehört genau zu einem Projekt.'
    calls=[]
    class Provider(ScriptedProvider):
        def __init__(self,*args):
            super().__init__();self.provider_id=args[0];self.model_id=args[3];self.input_tokens=self.output_tokens=0
        def run_role(self,role,context,schema):
            calls.append((role,context))
            result=super().run_role(role,context,schema)
            approved=any(item['response']==answer for item in context.get('human_clarifications',[]))
            if role=='requirements_engineer' and approved:result['requirements'][1]['text']=answer
            if role=='review_engineer' and not approved:
                target=next(item for item in result['assessments'] if item['target_key']=='REQ-0002')
                target.update(verdict='changes_required',question='Was bedeutet projektbezogen?',required_change='Zuordnung konkretisieren')
            return result
    monkeypatch.setattr('kusys.analysis.service.CrewAIProvider',Provider)
    client=TestClient(app);token=_login(client,'max.mustermann');headers={'X-CSRF-Token':token}
    tenant_id=client.get('/api/v1/project-creation-options').json()[0]['id']
    project=client.post('/api/v1/projects',headers=headers,json={'tenant_id':tenant_id,'project_number':f'ANSWERS-{uuid.uuid4()}','name':'Human review test'}).json()
    with SessionLocal() as db:
        tenant=db.get(Tenant,uuid.UUID(tenant_id));original_settings=dict(tenant.agent_settings);tenant.agent_settings={**original_settings,'max_rounds':1}
        review=ReviewRevision(tenant_id=tenant.id,project_id=uuid.UUID(project['id']),revision_no=1,status='approved');db.add(review);db.flush()
        for index,text in enumerate(('Das System muss Messwerte speichern.','Das System muss Aufnahmen projektbezogen speichern.')):
            db.add(Section(tenant_id=tenant.id,review_revision_id=review.id,order_index=index,category='requirement',source_text=text,normalized_text=text,edited_text=text))
        cfg=AIProviderConfig(tenant_id=tenant.id,provider='human-review-test',endpoint='https://example.invalid',allowed_models=['human-review-model'],encrypted_api_key=encrypt_secret('test',get_settings().master_key));db.add(cfg);db.flush();cfg_id=str(cfg.id)
        tom_id=str(db.scalar(select(User.id).where(User.username=='tom.mitglied')))
        db.commit()
    assert client.post(f"/api/v1/projects/{project['id']}/members",headers=headers,json={'user_id':tom_id,'role':'project_member'}).status_code==200
    created=client.post(f"/api/v1/projects/{project['id']}/analysis-runs",headers=headers,json={'provider_config_id':cfg_id,'model_id':'human-review-model'})
    assert created.status_code==202,created.text
    source=created.json()['analysis_run'];source_id=source['id']
    assert source['result']['quality']['status']=='blocked'
    endpoint=f'/api/v1/analysis-runs/{source_id}/review-responses'
    data=client.get(endpoint).json();assert data['can_respond'] and not data['can_recheck']
    finding=next(item for item in data['findings'] if item['target_key']=='REQ-0002')
    payload={'finding_id':finding['finding_id'],'response':answer,'expected_version':data['version']}
    assert client.post(f'/api/v1/analysis-runs/{source_id}/recheck',headers=headers).status_code==422
    assert client.post(endpoint,json=payload).status_code==403
    assert client.post(endpoint,headers=headers,json={**payload,'finding_id':'not-in-this-run'}).status_code==422
    assert client.post(endpoint,headers=headers,json={**payload,'response':'   '}).status_code==422
    member_token=_login(client,'tom.mitglied')
    assert not client.get(endpoint).json()['can_respond']
    assert client.post(endpoint,headers={'X-CSRF-Token':member_token},json=payload).status_code==403
    assert client.post(f'/api/v1/analysis-runs/{source_id}/recheck',headers={'X-CSRF-Token':member_token}).status_code==403
    token=_login(client,'max.mustermann');headers={'X-CSRF-Token':token}
    saved=client.post(endpoint,headers=headers,json=payload)
    assert saved.status_code==200,saved.text
    assert saved.json()['can_recheck']
    record=next(item for item in saved.json()['findings'] if item['finding_id']==finding['finding_id'])['answer']
    assert record['response']==answer and record['actor_name'] and record['answered_at']
    assert client.post(endpoint,headers=headers,json=payload).status_code==409
    assert client.post(f'/api/v1/analysis-runs/{source_id}/activate',headers=headers).status_code==422
    assert client.get(f"/api/v1/projects/{project['id']}/requirements").json()==[]
    calls.clear()
    rechecked=client.post(f'/api/v1/analysis-runs/{source_id}/recheck',headers=headers)
    assert rechecked.status_code==202,rechecked.text
    child=rechecked.json()['analysis_run'];result=child['result']
    assert child['id']!=source_id and result['quality']['status']=='accepted'
    assert calls[0][0]=='requirements_engineer' and calls[0][1]['previous']
    assert result['human_review']['answers'][0]['actor_id']==record['actor_id']
    assert result['quality']['review_cycle']=={'completed':1,'limit':1}
    assert [item['round'] for item in result['review_history']]==[1,2]
    with SessionLocal() as db:
        assert db.get(AnalysisRun,uuid.UUID(source_id)).result_json['quality']['status']=='blocked'
        step=db.scalar(select(AnalysisStep).where(AnalysisStep.analysis_run_id==uuid.UUID(source_id),AnalysisStep.step_name=='human_review'))
        assert step.result_json['version']==1 and len(step.result_json['history'])==1
        db.get(Tenant,uuid.UUID(tenant_id)).agent_settings=original_settings;db.commit()
    document=client.get(f"/api/v1/analysis-runs/{child['id']}/documentation")
    assert document.status_code==200 and answer in document.text and 'Fachliche Klarstellungen' in document.text
    assert client.post(f"/api/v1/analysis-runs/{child['id']}/activate",headers=headers).status_code==200
    assert client.get(f"/api/v1/projects/{project['id']}/work-packages").json()
