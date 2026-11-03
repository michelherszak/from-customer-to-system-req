from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum


class Priority(StrEnum):
    MUST = "muss"
    SHOULD = "soll"
    COULD = "kann"


class RelationType(StrEnum):
    REQUIRES = "requires"
    ENABLES = "enables"
    CONFLICTS_WITH = "conflicts_with"
    RELATED_TO = "related_to"
    REPLACES = "replaces"
    SPLIT_FROM = "split_from"


@dataclass(frozen=True, slots=True)
class Requirement:
    id: str
    key: str
    title: str
    text: str
    priority: Priority = Priority.SHOULD
    budget_eur: Decimal | None = None
    max_price_eur: Decimal | None = None
    active: bool = True


@dataclass(frozen=True, slots=True)
class RequirementRelation:
    source_id: str
    target_id: str
    relation_type: RelationType
    rationale: str | None = None


@dataclass(frozen=True, slots=True)
class RequirementAttribution:
    requirement_id: str
    cost_eur: Decimal
    sales_eur: Decimal
    margin_eur: Decimal
    budget_delta_eur: Decimal | None


@dataclass(slots=True)
class RequirementGraph:
    requirements: dict[str, Requirement] = field(default_factory=dict)
    relations: list[RequirementRelation] = field(default_factory=list)

    def add(self, requirement: Requirement) -> None:
        self.requirements[requirement.id] = requirement

    def link(self, relation: RequirementRelation) -> None:
        self.relations.append(relation)

    def transitive_dependents(self, requirement_id: str) -> set[str]:
        # A requires B means removing B affects A. Traverse incoming requires edges.
        reverse: dict[str, set[str]] = {}
        for rel in self.relations:
            if rel.relation_type is RelationType.REQUIRES:
                reverse.setdefault(rel.target_id, set()).add(rel.source_id)
        seen: set[str] = set()
        stack = list(reverse.get(requirement_id, set()))
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            stack.extend(reverse.get(current, set()) - seen)
        return seen
