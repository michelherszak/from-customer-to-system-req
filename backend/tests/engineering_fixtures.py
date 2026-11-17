"""Synthetic test data only. Never imported by the application."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
import re

from tests.engineering_rules import RuleBasedAnalysisProvider


@dataclass(frozen=True, slots=True)
class RequirementSuggestion:
    text: str
    priority: str
    title: str
    source_section_id: str

@dataclass(frozen=True, slots=True)
class WorkPackageSuggestion:
    name: str
    description: str
    role: str
    min_hours: int
    likely_hours: int
    max_hours: int
    phase: str
    requirement_indexes: tuple[int, ...]

@dataclass(frozen=True, slots=True)
class ClarificationSuggestion:
    text: str
    source_section_id: str

@dataclass(frozen=True, slots=True)
class AnalysisOutput:
    requirements: tuple[RequirementSuggestion, ...]
    work_packages: tuple[WorkPackageSuggestion, ...]
    clarifications: tuple[ClarificationSuggestion, ...]

    def to_json(self) -> dict:
        return {
            "requirements": [asdict(x) for x in self.requirements],
            "work_packages": [asdict(x) for x in self.work_packages],
            "clarifications": [asdict(x) for x in self.clarifications],
        }


class AIProvider(ABC):
    provider_id: str
    model_id: str

    @abstractmethod
    def analyze(self, sections: list[tuple[str, str]], language: str = "de") -> AnalysisOutput: ...


class DeterministicProvider(AIProvider):
    provider_id = "rule-based"
    model_id = "rule-based-v1"
    role_terms = {
        "software": "Software Engineering",
        "schnittstelle": "Software Engineering",
        "api": "Software Engineering",
        "elektr": "Electrical Engineering",
        "schalt": "Electrical Engineering",
        "mechan": "Mechanical Engineering",
        "sicherheit": "Safety Engineering",
        "security": "Security Engineering",
        "test": "Test Engineering",
        "abnahme": "Test Engineering",
        "dokument": "Documentation",
    }

    def analyze(self, sections: list[tuple[str, str]], language: str = "de") -> AnalysisOutput:
        requirements: list[RequirementSuggestion] = []
        clarifications: list[ClarificationSuggestion] = []
        fallback = RuleBasedAnalysisProvider()
        for section_id, text in sections:
            for item in fallback.extract_requirements(text):
                normalized = item.text.strip()
                title = re.sub(r"^(Das System soll|The system shall)\s+", "", normalized, flags=re.I)
                title = title[:90].rstrip(" .") or "Anforderung"
                requirements.append(RequirementSuggestion(normalized, item.priority, title, section_id))
            if re.search(r"\b(TBD|TBC|unklar|offen|to be defined|to be clarified)\b", text, re.I):
                clarifications.append(ClarificationSuggestion(f"Klärung erforderlich: {text[:220]}", section_id))
        # Fallback must never silently drop approved requirement sections. If modal detection failed,
        # treat the entire approved section as a requirement with a review-oriented priority.
        covered = {x.source_section_id for x in requirements}
        for section_id, text in sections:
            if section_id not in covered and text.strip():
                prefix = "Das System soll " if language.lower().startswith("de") else "The system shall "
                cleaned = text.strip().rstrip(".")
                requirements.append(RequirementSuggestion(prefix + cleaned + ".", "soll", cleaned[:90], section_id))
        packages: list[WorkPackageSuggestion] = []
        for i, req in enumerate(requirements):
            role = self._role_for(req.text)
            likely = self._hours_for(req.text)
            packages.append(WorkPackageSuggestion(
                name=f"Umsetzung {req.title}"[:300],
                description=f"Arbeitspaket zur Anforderung: {req.text}",
                role=role,
                min_hours=max(0, int(likely * 0.7)),
                likely_hours=likely,
                max_hours=max(likely, int(likely * 1.5)),
                phase="Realisierung",
                requirement_indexes=(i,),
            ))
        return AnalysisOutput(tuple(requirements), tuple(packages), tuple(clarifications))

    def _role_for(self, text: str) -> str:
        low = text.lower()
        for term, role in self.role_terms.items():
            if term in low: return role
        return "Systems Engineering"

    @staticmethod
    def _hours_for(text: str) -> int:
        n = len(text)
        base = 16 if n < 120 else 32 if n < 300 else 48
        if re.search(r"\b(muss|must|shall)\b", text, re.I): base += 8
        return base

def _offline(role, context, provider):
    """Transparent draft mode: never claims a substantive AI review."""
    if role == "requirements_engineer":
        output = provider.analyze([(x["id"], x["text"]) for x in context["sections"]], context["language"])
        return {"requirements": [{"key": f"REQ-{i:04d}", "title": x.title, "text": x.text, "priority": x.priority, "category": "requirement", "source_section_id": x.source_section_id} for i, x in enumerate(output.requirements, 1)], "clarifications": [{"text": x.text, "source_section_id": x.source_section_id} for x in output.clarifications]}
    if role == "systems_engineer":
        systems = [{"key": f"SYS-{i:04d}", "title": x["title"], "text": x["text"], "parent_keys": [x["key"]], "rationale": "Vorläufige 1:1-Übernahme; technische Zerlegung fehlt im Offline-Modus.", "verification_method": "inspection", "verification_criterion": "Fachlich festzulegen: objektiver Nachweis der Kundenanforderung.", "assumptions": ["Keine KI-Ableitung; technische Prüfung durch Projektleitung erforderlich."]} for i, x in enumerate(context["requirements"], 1)]
        return {"system_requirements": systems, "architecture": [{"key": "ARC-001", "name": "Systemgrenze (Entwurf)", "description": "Komponenten und Schnittstellen sind fachlich festzulegen.", "covers": [x["key"] for x in systems], "interfaces": []}]}
    if role == "work_planner":
        return {"work_packages": [{"key": f"AP-{i:04d}", "name": "Umsetzung: " + x["title"], "description": x["text"], "role": provider._role_for(x["text"]), "min_hours": int(provider._hours_for(x["text"]) * .7), "likely_hours": provider._hours_for(x["text"]), "max_hours": int(provider._hours_for(x["text"]) * 1.5), "phase": "Realisierung", "system_requirement_keys": [x["key"]], "depends_on": [], "estimate_basis": "Offline-Heuristik nach Textlänge, keine belastbare Projektschätzung.", "assumptions": ["Ressourcen, Integration, Verifikation und Dokumentation fachlich nachschätzen."], "risks": ["Umfang und technische Lösung ungeprüft."]} for i, x in enumerate(context["system_requirements"], 1)]}
    fields = ("source_fidelity", "necessity", "completeness", "feasibility", "verifiability", "sizing")
    return {"summary": "Offline-Entwurf: keine unabhängige fachliche KI-Prüfung durchgeführt.", "assessments": [{"target_key": x["key"], "owner": owner, "verdict": "accepted_with_assumptions", **{f: "Ungeprüft: fachliche Bestätigung erforderlich (Offline-Modus)." for f in fields}, "question": "", "required_change": ""} for field, owner in (("requirements", "requirements_engineer"), ("system_requirements", "systems_engineer"), ("work_packages", "work_planner")) for x in context[field]]}
