from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
import re

from kusys.analysis.rule_based import RuleBasedAnalysisProvider


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

class OpenAICompatibleProvider(AIProvider):
    """Provider for OpenAI-compatible chat-completions endpoints.

    The adapter deliberately depends only on the Python standard library so the deterministic
    fallback remains deployable offline. The remote model is required to return JSON only.
    """
    def __init__(self, provider_id: str, endpoint: str, api_key: str, model_id: str, timeout_seconds: int = 90):
        self.provider_id=provider_id;self.endpoint=endpoint.rstrip('/');self.api_key=api_key;self.model_id=model_id;self.timeout_seconds=timeout_seconds
        self.input_tokens=0;self.output_tokens=0

    def analyze(self, sections: list[tuple[str, str]], language: str = "de") -> AnalysisOutput:
        import json, urllib.request
        schema={"requirements":[{"text":"string","priority":"muss|soll|kann","title":"string","source_section_id":"string"}],"work_packages":[{"name":"string","description":"string","role":"string","min_hours":0,"likely_hours":0,"max_hours":0,"phase":"Konzept|Spezifikation|Realisierung|Integration|Abnahme|Übergreifend","requirement_indexes":[0]}],"clarifications":[{"text":"string","source_section_id":"string"}]}
        system=("Du bist Requirements Engineer und Projektplaner. Gib ausschließlich valides JSON ohne Markdown zurück. "
                "Erzeuge atomare Anforderungen, nachvollziehbare Arbeitspakete und Klärungspunkte. Schema: "+json.dumps(schema,ensure_ascii=False))
        user=json.dumps({"language":language,"sections":[{"id":sid,"text":text} for sid,text in sections]},ensure_ascii=False)
        payload=json.dumps({"model":self.model_id,"temperature":0,"response_format":{"type":"json_object"},"messages":[{"role":"system","content":system},{"role":"user","content":user}]},ensure_ascii=False).encode('utf-8')
        url=self.endpoint if self.endpoint.endswith('/chat/completions') else self.endpoint+'/chat/completions'
        req=urllib.request.Request(url,data=payload,headers={"Authorization":f"Bearer {self.api_key}","Content-Type":"application/json"},method='POST')
        with urllib.request.urlopen(req,timeout=self.timeout_seconds) as response:
            raw=json.loads(response.read().decode('utf-8'))
        usage=raw.get('usage') or {};self.input_tokens+=int(usage.get('prompt_tokens') or usage.get('input_tokens') or 0);self.output_tokens+=int(usage.get('completion_tokens') or usage.get('output_tokens') or 0)
        content=raw['choices'][0]['message']['content'];data=json.loads(content)
        reqs=[]
        for x in data.get('requirements',[]):
            reqs.append(RequirementSuggestion(str(x['text']),str(x.get('priority','soll')),str(x.get('title') or 'Anforderung')[:300],str(x['source_section_id'])))
        wps=[]
        for x in data.get('work_packages',[]):
            mn=max(0,int(x.get('min_hours',0)));likely=max(mn,int(x.get('likely_hours',mn)));mx=max(likely,int(x.get('max_hours',likely)))
            wps.append(WorkPackageSuggestion(str(x.get('name') or 'Arbeitspaket')[:300],str(x.get('description') or ''),str(x.get('role') or 'Systems Engineering'),mn,likely,mx,str(x.get('phase') or 'Realisierung'),tuple(int(i) for i in x.get('requirement_indexes',[]))))
        cls=tuple(ClarificationSuggestion(str(x.get('text') or ''),str(x['source_section_id'])) for x in data.get('clarifications',[]) if x.get('source_section_id'))
        if not reqs: raise ValueError('Provider lieferte keine Anforderungen')
        return AnalysisOutput(tuple(reqs),tuple(wps),cls)
