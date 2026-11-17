"""Engineering dossier generated from the persisted run, never re-inferred."""
import json

def render_documentation(run) -> str:
    from kusys.analysis.derivation import assessed_result
    result = assessed_result(run.result_json or {})
    quality = result.get("quality", {})
    lines = ["# KuSys Engineering-Dokumentation", f"Lauf: {run.id}", f"Projekt: {run.project_id}", f"Prüfschrittrevision: {run.review_revision_id}", f"Provider / Modell: {run.provider} / {run.model_id}", f"Schema: {run.schema_version}", f"Qualität: {quality.get('status', 'legacy')}", "", "## Zusammenfassung", quality.get("summary", ""), ""]
    for title, field in (("Kundenanforderungen", "requirements"), ("Systemanforderungen und Verifikation", "system_requirements"), ("Architektur", "architecture"), ("Arbeitspakete und Schätzgrundlagen", "work_packages")):
        lines += [f"## {title}"]
        for item in result.get(field, []):
            lines += [f"### {item.get('key', '')} {item.get('title', item.get('name', ''))}"]
            lines += [f"- {key}: {json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value}" for key, value in item.items()]
            lines.append("")
    lines += ["## Aufwand, Budget und Zeit", json.dumps(result.get("estimate_summary", {}), ensure_ascii=False), "Kosten und Kalendertermine hängen von Rate Card, Ressourcen und Kalendern ab; Personenstunden sind keine Durchlaufzeit.", "", "## Review-Historie"]
    for rnd in result.get("review_history", []):
        lines += [f"### Runde {rnd['round']}", rnd["review"]["summary"]]
        for item in rnd["review"]["assessments"]:
            lines += [f"#### {item['target_key']} — {item['owner']} — {item['verdict']}"]
            lines += [f"- {key}: {value}" for key, value in item.items() if key not in {"target_key", "owner", "verdict"}]
        lines += ["Offene Befunde:", json.dumps(rnd["findings"], ensure_ascii=False, indent=2)]
    if result.get("human_review"):
        lines += ["## Fachliche Klarstellungen der Projektleitung"]
        for answer in result["human_review"].get("answers", []):
            lines += [f"### {answer['target_key']} · {answer['owner']}", f"Frage: {answer['question']}", f"Antwort: {answer['response']}", f"Beantwortet von {answer['actor_name']} ({answer['actor_id']}) am {answer['answered_at']}", f"Ursprungslauf: {answer['source_run_id']}", ""]
    # Machine-readable snapshot preserves all previous versions and trace links too.
    lines += ["", "## Vollständiger reproduzierbarer Ergebnisstand", "```json", json.dumps(result, ensure_ascii=False, indent=2), "```"]
    return "\n".join(lines)
