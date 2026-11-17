"""Four roles, three review rounds maximum, immutable evidence and hard traceability gates."""
from __future__ import annotations

from copy import deepcopy
from typing import Callable
from kusys.analysis.contracts import Requirements
from kusys.analysis.prompts import PROMPT_VERSION

MAX_ROUNDS = 3


def checks(result: dict, sections: list[tuple[str, str]], role_names: list[str] | None = None) -> list[dict]:
    """Code gates cannot be waived by the language model."""
    issues = []
    def add(target, owner, message):
        issues.append({"target_key": target, "owner": owner, "verdict": "blocked", "question": message, "required_change": message, "origin": "code_gate"})
    reqs = result.get("requirements", [])
    systems = result.get("system_requirements", [])
    arch = result.get("architecture", [])
    packages = result.get("work_packages", [])
    sources = {sid for sid, _ in sections}
    groups = [(reqs, "requirements_engineer"), (systems, "systems_engineer"), (arch, "systems_engineer"), (packages, "work_planner")]
    all_ids = set()
    for items, owner in groups:
        for item in items:
            key = item["key"]
            if key in all_ids:
                add(key, owner, "ID mehrfach vergeben")
            all_ids.add(key)
    req_ids = {x["key"] for x in reqs}
    sys_ids = {x["key"] for x in systems}
    ap_ids = {x["key"] for x in packages}
    covered_sources = set()
    for req in reqs:
        if req["source_section_id"] not in sources:
            add(req["key"], "requirements_engineer", "Quellen-ID ist kein freigegebener Anforderungsabschnitt")
        covered_sources.add(req["source_section_id"])
    for sid in sorted(sources - covered_sources):
        add(sid, "requirements_engineer", "Freigegebener Anforderungsabschnitt wurde nicht übernommen")
    parents = set()
    for sys in systems:
        parents.update(sys["parent_keys"])
        if set(sys["parent_keys"]) - req_ids:
            add(sys["key"], "systems_engineer", "Systemanforderung verweist auf unbekannte REQ")
    for key in sorted(req_ids - parents):
        add(key, "systems_engineer", "Kundenanforderung ohne Systemableitung")
    for item in arch:
        if set(item["covers"]) - sys_ids:
            add(item["key"], "systems_engineer", "Architektur verweist auf unbekannte SYS")
    for key in sorted(sys_ids - {k for x in arch for k in x["covers"]}):
        add(key, "systems_engineer", "Systemanforderung keinem Architekturelement zugeordnet")
    planned = set()
    for wp in packages:
        planned.update(wp["system_requirement_keys"])
        if role_names is not None and wp["role"] not in role_names:
            add(wp["key"], "work_planner", "Fachrolle fehlt in der Projekt-Rate-Card")
        if set(wp["system_requirement_keys"]) - sys_ids:
            add(wp["key"], "work_planner", "Arbeitspaket verweist auf unbekannte SYS")
        if not wp["min_hours"] <= wp["likely_hours"] <= wp["max_hours"]:
            add(wp["key"], "work_planner", "Aufwandsspanne muss Minimum ≤ wahrscheinlich ≤ Maximum erfüllen")
        if set(wp["depends_on"]) - ap_ids or wp["key"] in wp["depends_on"]:
            add(wp["key"], "work_planner", "Ungültige Arbeitspaket-Abhängigkeit")
    for key in sorted(sys_ids - planned):
        add(key, "work_planner", "Systemanforderung ohne Arbeitspaket")
    remaining = {x["key"]: set(x["depends_on"]) for x in packages}
    while remaining:
        ready = {key for key, deps in remaining.items() if not deps}
        if not ready:
            add("PLAN", "work_planner", "Zyklische Arbeitspaket-Abhängigkeiten")
            break
        remaining = {key: deps - ready for key, deps in remaining.items() if key not in ready}
    from kusys.analysis.derivation import derivation_findings
    issues.extend(derivation_findings(result))
    return issues


def review_checks(review: dict, result: dict) -> list[dict]:
    expected = {x["key"]: owner for field, owner in (("requirements", "requirements_engineer"), ("system_requirements", "systems_engineer"), ("work_packages", "work_planner")) for x in result[field]}
    seen = set()
    issues = []
    for item in review["assessments"]:
        key = item["target_key"]
        if key in seen or key not in expected or item["owner"] != expected.get(key):
            issues.append({"target_key": key, "owner": "review_engineer", "verdict": "blocked", "question": "Review-Ziel fehlt, ist doppelt oder falsch zugeordnet", "origin": "code_gate"})
        seen.add(key)
        if item["verdict"] in {"blocked", "changes_required"} and (not item["question"].strip() or not item["required_change"].strip()):
            issues.append({"target_key": key, "owner": "review_engineer", "verdict": "blocked", "question": "Review-Befund braucht Rückfrage und konkrete Korrektur", "origin": "code_gate"})
    for key in sorted(set(expected) - seen):
        issues.append({"target_key": key, "owner": "review_engineer", "verdict": "blocked", "question": "Einzelprüfung fehlt", "origin": "code_gate"})
    return issues




def run_workflow(sections, provider, language="de", project=None, on_step: Callable | None = None, max_rounds=MAX_ROUNDS, max_chars=60000, checkpoints=None, review_seed=None, human_review=None):
    """Run all roles, route feedback and retain every reviewed snapshot."""
    if not sections:
        raise ValueError("Keine freigegebenen Anforderungsabschnitte")
    if not callable(getattr(provider, "run_role", None)):
        raise ValueError("Echtes KI-Modell erforderlich. Regelbasierter Ersatz ist für Systemableitungen gesperrt.")
    result = {"requirements": [], "system_requirements": [], "architecture": [], "work_packages": [], "clarifications": []}
    history = deepcopy((review_seed or {}).get("review_history", []))
    if review_seed:
        for field in result:
            result[field] = deepcopy(review_seed.get(field, []))
        for package in result["work_packages"]:
            package.pop("requirement_indexes", None)
    previous_rounds = len(history)
    first_round = max((item["round"] for item in history), default=0) + 1
    def call(role, context, schema, round_no):
        from kusys.analysis.checkpoints import input_key, source_keys
        key = input_key(role, context, schema, provider)
        # callback before network call allows cancellation and durable progress
        if on_step:
            on_step(role, round_no, "running", {"input_key": key, "batch": context.get("batch"), "source_keys": source_keys(context), "target_keys": context.get("target_keys", [])})
        try:
            cached = checkpoints.get(key, role, round_no, context, schema) if checkpoints else None
            if cached is not None:
                if on_step:
                    on_step(role, round_no, "cached", deepcopy(cached))
                return cached
            raw = provider.run_role(role, context, schema)
            validated = schema.model_validate(raw).model_dump(mode="json")
        except Exception as exc:
            if on_step:
                from kusys.analysis.providers import ProviderExecutionError
                detail = {"error_type": type(exc).__name__, "message": "Modellaufruf oder Prüfung des Ausgabeformats fehlgeschlagen. Keine Ergebnisse übernommen."}
                if isinstance(exc, ProviderExecutionError):
                    detail.update(error_code=exc.diagnostic_code, http_status=exc.http_status, message=exc.diagnostic_message, validation_issues=exc.validation_issues, upstream_status=exc.upstream_status)
                on_step(role, round_no, "failed", detail)
            raise
        if on_step:
            on_step(role, round_no, "succeeded", deepcopy(validated))
        return validated
    base = {"language": language, "project": project or {}}
    if human_review and human_review.get("answers"):
        base["human_clarifications"] = human_review["answers"]
        base["clarification_policy"] = "Diese Antworten sind dokumentierte fachliche Klarstellungen der Projektleitung und ergänzen die Originalquellen. Behalte Original-Quellen-IDs bei und mache Klarstellungen in der Ableitung nachvollziehbar. Antworten sind keine Freigabe: Prüfe, ob Befunde tatsächlich behoben wurden; technische Prüfregeln bleiben verbindlich."

    # Extract in bounded source chunks, then review against the complete requirement graph.
    chunks, current, count = [], [], 0
    for sid, text in sections:
        if len(text) > max_chars:
            raise ValueError("Anforderungsabschnitt überschreitet Blockgröße; bitte im Prüfschritt aufteilen")
        if current and count + len(text) > max_chars:
            chunks.append(current)
            current, count = [], 0
        current.append({"id": sid, "text": text})
        count += len(text)
    chunks.append(current)
    if not review_seed:
        for index, chunk in enumerate(chunks, 1):
            out = call("requirements_engineer", {**base, "sections": chunk, "batch": {"index": index, "count": len(chunks)}}, Requirements, 1)
            for req in out["requirements"]:
                # IDs are assigned before any downstream reference is created.
                req["key"] = f"REQ-{len(result['requirements']) + 1:04d}"
                result["requirements"].append(req)
            result["clarifications"].extend(out["clarifications"])
    feedback = deepcopy((review_seed or {}).get("quality", {}).get("findings", []))
    limit = min(MAX_ROUNDS, max(1, max_rounds))
    last_round = first_round + limit - 1
    for round_no in range(first_round, last_round + 1):
        if round_no > 1 and any(x["owner"] == "requirements_engineer" for x in feedback):
            revised = call("requirements_engineer", {**base, "sections": [{"id": sid, "text": text} for sid, text in sections], "previous": result["requirements"], "feedback": feedback}, Requirements, round_no)
            result.update(revised)
        from kusys.analysis.batches import derive_systems, plan_work, review_all
        if not review_seed or round_no != first_round or any(item["owner"] in {"requirements_engineer", "systems_engineer"} for item in feedback):
            design = derive_systems(call,base,result["requirements"],result["system_requirements"],[x for x in feedback if x["owner"]=="systems_engineer"],round_no)
            result.update(design)
        from kusys.analysis.derivation import derivation_findings
        if derivation_findings(result):
            # Do not spend another model call estimating a copied design.
            result["work_packages"] = []
        else:
            plan = plan_work(call,base,result,[x for x in feedback if x["owner"]=="work_planner"],round_no)
            result.update(plan)
        review = review_all(call,base,result,history,checks(result,sections,(project or {}).get("roles")),round_no)
        gates = checks(result, sections, (project or {}).get("roles"))
        # Only SYS review findings enter the sparring loop; REQ/AP reviews are ignored.
        feedback = gates + [x for x in review["assessments"] if x["owner"] == "systems_engineer" and x["target_key"].startswith("SYS-") and x["verdict"] in {"blocked", "changes_required"}]
        # An open source question cannot be silently approved by the reviewer.
        for item in result["clarifications"]:
            feedback.append({"target_key": item.get("source_section_id", "REQ"), "owner": "requirements_engineer", "verdict": "blocked", "question": item.get("text", "Offene Quellenklärung"), "origin": "clarification"})
        snapshot = {"round": round_no, "artifacts": deepcopy(result), "review": review, "findings": deepcopy(feedback)}
        history.append(snapshot)
        if on_step:
            on_step("review_round", round_no, "succeeded", deepcopy(snapshot))
        if not feedback:
            break
    provisional = any(x["verdict"] == "accepted_with_assumptions" for x in review["assessments"]) or any(x["assumptions"] for x in result["system_requirements"]) or any(x["assumptions"] for x in result["work_packages"])
    result["quality"] = {"status": "blocked" if feedback else "needs_human_review" if provisional else "accepted", "offline": False, "max_rounds": last_round, "rounds_completed": len(history), "prompt_version": PROMPT_VERSION, "engine": getattr(provider, "engine", "test"), "findings": feedback, "summary": review["summary"]}
    if human_review and human_review.get("answers"):
        result["human_review"] = deepcopy(human_review)
        result["quality"]["review_cycle"] = {"completed":len(history)-previous_rounds,"limit":limit}
    result["review_history"] = history
    req_index = {x["key"]: i for i, x in enumerate(result["requirements"])}
    sys_by_key = {x["key"]: x for x in result["system_requirements"]}
    for wp in result["work_packages"]:
        wp["requirement_indexes"] = sorted({req_index[parent] for key in wp["system_requirement_keys"] if key in sys_by_key for parent in sys_by_key[key]["parent_keys"] if parent in req_index})
    result["estimate_summary"] = {"min_hours": sum(x["min_hours"] for x in result["work_packages"]), "likely_hours": sum(x["likely_hours"] for x in result["work_packages"]), "max_hours": sum(x["max_hours"] for x in result["work_packages"]), "basis": "Personenstunden; Kosten aus Rate Card, Termine aus Ressourcen und Kalendern berechnen."}
    return result
