from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True, slots=True)
class ExtractedRequirement:
    text: str
    priority: str


class RuleBasedAnalysisProvider:
    """Deterministic offline fallback; no model/API key required."""

    MUST = re.compile(r"\b(muss|must|shall|required)\b", re.I)
    SHOULD = re.compile(r"\b(soll|should)\b", re.I)

    def extract_requirements(self, text: str) -> list[ExtractedRequirement]:
        out: list[ExtractedRequirement] = []
        for raw in re.split(r"(?<=[.!?])\s+|\n+", text):
            sentence = raw.strip()
            if not sentence:
                continue
            if self.MUST.search(sentence):
                out.append(ExtractedRequirement(sentence, "muss"))
            elif self.SHOULD.search(sentence):
                out.append(ExtractedRequirement(sentence, "soll"))
        return out
