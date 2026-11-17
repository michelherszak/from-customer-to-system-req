from copy import deepcopy
import pytest
from pydantic import ValidationError
from tests.engineering_fixtures import DeterministicProvider, _offline
from kusys.analysis.workflow import run_workflow, checks

SECTIONS = [("s1", "Das System muss 10 Teile pro Minute transportieren."), ("s2", "Das System soll Fehler protokollieren.")]

class ScriptedProvider:
    provider_id = "scripted"
    model_id = "test"
    def __init__(self, change_owner=None, always_block=False, bad_source=False, missing_review=False):
        self.calls = []
        self.change_owner = change_owner
        self.always_block = always_block
        self.bad_source = bad_source
        self.missing_review = missing_review
        self.reviews = 0
    def run_role(self, role, context, schema):
        self.calls.append((role, deepcopy(context)))
        raw = _offline(role, context, DeterministicProvider())
        if role == "requirements_engineer" and self.bad_source:
            raw["requirements"][0]["source_section_id"] = "context-not-approved"
        if role == "systems_engineer":
            for item in raw["system_requirements"]:
                item["text"] = f"Der Dienst für {item['key']} validiert Eingangsdaten, verarbeitet sie transaktional und liefert ein versioniertes Ergebnis über eine dokumentierte Schnittstelle."
                item["assumptions"] = []
                item["rationale"] = "Kundenvorgabe erfordert diese Systemfunktion."
                item["verification_criterion"] = "Gemessene Förderleistung mindestens 10 Teile/Minute im vereinbarten Betriebsfall."
        if role == "work_planner":
            for item in raw["work_packages"]:
                item["assumptions"] = []
                item["estimate_basis"] = "Referenzprojekt: 8 h Implementierung und 8 h Verifikation."
        if role == "review_engineer":
            self.reviews += 1
            for item in raw["assessments"]:
                item["verdict"] = "accepted"
                if item["owner"] == self.change_owner and (self.reviews == 1 or self.always_block):
                    item.update(verdict="changes_required", question="Ist die Dimensionierung belegt?", required_change="Schätzgrundlage bzw. Ableitung konkret begründen.")
            raw["summary"] = "Jede Anforderung und jedes Paket einzeln geprüft."
            if self.missing_review:
                raw["assessments"] = raw["assessments"][:1]
        return raw


def test_full_trace_and_individual_review():
    out = run_workflow(SECTIONS, ScriptedProvider())
    assert out["quality"]["status"] == "accepted"
    assert out["quality"]["rounds_completed"] == 1
    assert not checks(out, SECTIONS)
    assert len(out["review_history"][0]["review"]["assessments"]) == 6
    assert out["work_packages"][0]["requirement_indexes"] == [0]
    assert out["system_requirements"][0]["parent_keys"] == ["REQ-0001"]


@pytest.mark.parametrize("owner", ["requirements_engineer", "systems_engineer", "work_planner"])
def test_feedback_routes_to_owner_and_is_reviewed_again(owner):
    provider = ScriptedProvider(change_owner=owner)
    out = run_workflow(SECTIONS, provider)
    assert out["quality"]["status"] == "accepted"
    assert len(out["review_history"]) == 2
    assert out["review_history"][0]["findings"]
    assert out["review_history"][1]["findings"] == []
    assert any(role == owner and context.get("feedback") for role, context in provider.calls)
    assert out["review_history"][0]["artifacts"]["system_requirements"]


def test_loop_stops_at_three_rounds_with_blockers():
    out = run_workflow(SECTIONS, ScriptedProvider(change_owner="systems_engineer", always_block=True))
    assert out["quality"]["status"] == "blocked"
    assert out["quality"]["rounds_completed"] == 3
    assert out["quality"]["findings"]


def test_unapproved_source_cannot_be_approved_by_model():
    out = run_workflow(SECTIONS, ScriptedProvider(bad_source=True))
    assert out["quality"]["status"] == "blocked"
    assert any(x.get("origin") == "code_gate" for x in out["quality"]["findings"])


def test_review_must_cover_every_single_artifact():
    out = run_workflow(SECTIONS, ScriptedProvider(missing_review=True))
    assert out["quality"]["status"] == "blocked"
    assert any(x["question"] == "Einzelprüfung fehlt" for x in out["quality"]["findings"])


def test_offline_never_claims_independent_review():
    with pytest.raises(ValueError, match="Echtes KI-Modell"):
        run_workflow(SECTIONS, DeterministicProvider())


def test_unknown_links_bad_estimates_and_cycles_are_blocked():
    out = run_workflow(SECTIONS, ScriptedProvider())
    out["system_requirements"][0]["parent_keys"] = ["REQ-UNKNOWN"]
    out["work_packages"][0]["min_hours"] = 999
    out["work_packages"][0]["depends_on"] = ["AP-0002"]
    out["work_packages"][1]["depends_on"] = ["AP-0001"]
    messages = [x["question"] for x in checks(out, SECTIONS)]
    assert "Systemanforderung verweist auf unbekannte REQ" in messages
    assert "Zyklische Arbeitspaket-Abhängigkeiten" in messages
    assert any("Minimum" in x for x in messages)


def test_required_text_and_verification_cannot_be_silently_filled():
    class BrokenProvider(ScriptedProvider):
        def run_role(self, role, context, schema):
            raw = super().run_role(role, context, schema)
            if role == "systems_engineer":
                del raw["system_requirements"][0]["verification_criterion"]
            return raw
    with pytest.raises(ValidationError):
        run_workflow(SECTIONS, BrokenProvider())


def test_chunking_keeps_ids_unique_and_all_sources_reviewed():
    out = run_workflow(SECTIONS, ScriptedProvider(), max_chars=70)
    assert len({x["key"] for x in out["requirements"]}) == 2
    assert {x["source_section_id"] for x in out["requirements"]} == {"s1", "s2"}


def test_callback_allows_cancel_before_next_role():
    def cancel(role, number, status, output):
        if role == "systems_engineer" and status == "running":
            raise RuntimeError("cancelled")
    with pytest.raises(RuntimeError, match="cancelled"):
        run_workflow(SECTIONS, ScriptedProvider(), on_step=cancel)


def test_copied_system_requirement_is_rejected():
    out = run_workflow(SECTIONS, ScriptedProvider())
    out["system_requirements"][0]["text"] = out["requirements"][0]["text"]
    assert any(x.get("origin") == "derivation_gate" for x in checks(out, SECTIONS))


def test_old_offline_results_are_rejected_without_rewriting_history():
    from kusys.analysis.derivation import assessed_result
    old = {"quality": {"offline": True, "status": "needs_human_review"}, "requirements": [{"key":"REQ-1", "text":"Das System muss lokal laufen."}], "system_requirements":[{"key":"SYS-1", "text":"Das System muss lokal laufen.", "parent_keys":["REQ-1"]}]}
    assessed = assessed_result(old)
    assert assessed["quality"]["status"] == "blocked"
    assert len(assessed["quality"]["findings"]) == 2
    assert old["quality"]["status"] == "needs_human_review"


def test_large_derivation_is_bounded_and_all_links_survive():
    sections=[(f"s{i}",f"Das System muss den Vorgang {i} nachweisbar bearbeiten.") for i in range(23)]
    provider=ScriptedProvider()
    out=run_workflow(sections,provider)
    assert out["quality"]["status"]=="accepted"
    assert len(out["requirements"])==23 and len(out["system_requirements"])==23
    assert len({x["key"] for x in out["system_requirements"]})==23
    assert not checks(out,sections)
    for role,context in provider.calls:
        if role=="systems_engineer":assert len(context["requirements"])<=10
        if role=="work_planner":assert len(context["system_requirements"])<=10
        if role=="review_engineer":assert sum(len(context.get(k,[])) for k in ("requirements","system_requirements","work_packages"))<=10
    assert len(out["review_history"][0]["review"]["assessments"])==69


def test_diagnostic_events_include_batch_and_failure_without_source_content():
    events=[]
    class FailingProvider(ScriptedProvider):
        def run_role(self, role, context, schema):
            if role == "systems_engineer":
                raise ValueError("secret-customer-content")
            return super().run_role(role,context,schema)
    with pytest.raises(ValueError):
        run_workflow(SECTIONS, FailingProvider(), on_step=lambda *args:events.append(args))
    assert events[0][3]["batch"] == {"index":1,"count":1}
    assert events[0][3]["source_keys"] == ["s1","s2"]
    assert events[-1][0:3] == ("systems_engineer",1,"failed")
    assert events[-1][3]["error_type"] == "ValueError"
    assert "secret-customer-content" not in str(events[-1][3])
