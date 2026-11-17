"""Reject copied requirements and expose historical replacement-mode results honestly."""
from copy import deepcopy
from difflib import SequenceMatcher
import re


def normalize(text):
    return re.sub(r"[^\w]+", " ", str(text).casefold()).strip()


def derivation_findings(result):
    requirements = {item.get("key"): item for item in result.get("requirements", [])}
    findings = []
    if (result.get("quality") or {}).get("offline"):
        findings.append({"target_key": "ANALYSE", "owner": "systems_engineer", "verdict": "blocked", "origin": "derivation_gate", "question": "Abgelehnt: Dieser Lauf verwendete Regelcode statt eines KI-Modells. Es fand keine technische Ableitung statt.", "required_change": "Vollständige Absätze aufbereiten und mit einem konfigurierten KI-Modell neu ableiten."})
    for system in result.get("system_requirements", []):
        text = normalize(system.get("text", ""))
        for parent in system.get("parent_keys", []):
            source = normalize(requirements.get(parent, {}).get("text", ""))
            if source and (text == source or min(len(text), len(source)) >= 50 and SequenceMatcher(None, source, text, autojunk=False).ratio() >= .94):
                findings.append({"target_key": system.get("key", "SYS"), "owner": "systems_engineer", "verdict": "blocked", "origin": "derivation_gate", "question": f"Ableitung abgelehnt: Systemanforderung ist wortgleich oder nahezu wortgleich mit {parent}.", "required_change": "Technisches Verhalten, zuständige Komponente/Schnittstelle und objektives Nachweiskriterium ableiten; keine bloße Umformulierung."})
                break
    return findings


def assessed_result(result):
    """Revalidate old runs for display/download without changing historical records."""
    if not result:
        return result
    out = deepcopy(result)
    findings = derivation_findings(out)
    if findings:
        quality = out.setdefault("quality", {})
        quality["status"] = "blocked"
        quality["summary"] = "Ableitung abgelehnt: Regelbasierter Ersatz oder kopierte Kundenanforderungen. Ein neuer Modelllauf ist erforderlich."
        current = [x for x in quality.get("findings", []) if x.get("origin") != "derivation_gate"]
        quality["findings"] = current + findings
        quality["derivation_rejected"] = True
    return out
