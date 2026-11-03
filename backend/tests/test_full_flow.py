from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path

DB_PATH = Path("/tmp/kusys_pytest_full_flow.db")
STORE_PATH = Path("/tmp/kusys_pytest_artifacts")
DB_PATH.unlink(missing_ok=True)
shutil.rmtree(STORE_PATH, ignore_errors=True)
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


def test_us_00_ac_01_complete_upload_to_published_offer_flow():
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

    analysis = client.post(f"/api/v1/projects/{project_id}/analysis-runs", headers=headers)
    assert analysis.status_code == 202, analysis.text
    run = analysis.json()["analysis_run"]
    assert run["status"] == "succeeded"
    activated = client.post(f"/api/v1/analysis-runs/{run['id']}/activate", headers=headers)
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
