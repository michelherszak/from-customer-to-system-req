"""Versioned contracts for the four-role engineering workflow."""
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]

class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")

class CustomerRequirement(Contract):
    key: Text
    title: Text
    text: Text
    priority: Literal["muss", "soll", "kann"] = "soll"
    source_section_id: Text
    category: Literal["requirement"] = "requirement"

class Clarification(Contract):
    source_section_id: Text
    text: Text


class Requirements(Contract):
    requirements: list[CustomerRequirement] = Field(min_length=1)
    clarifications: list[Clarification] = Field(default_factory=list)

class SystemRequirement(Contract):
    key: Text
    title: Text
    text: Text
    parent_keys: list[Text] = Field(min_length=1)
    rationale: Text
    verification_method: Literal["test", "analysis", "inspection", "demonstration"]
    verification_criterion: Text
    assumptions: list[Text] = Field(default_factory=list)

class ArchitectureItem(Contract):
    key: Text
    name: Text
    description: Text
    covers: list[Text] = Field(min_length=1)
    interfaces: list[Text] = Field(default_factory=list)

class SystemDesign(Contract):
    system_requirements: list[SystemRequirement] = Field(min_length=1)
    architecture: list[ArchitectureItem] = Field(min_length=1)

class Package(Contract):
    key: Text
    name: Text
    description: Text
    role: Text
    min_hours: int = Field(ge=0)
    likely_hours: int = Field(ge=0)
    max_hours: int = Field(ge=0)
    phase: Literal["Konzept", "Spezifikation", "Realisierung", "Integration", "Abnahme", "Übergreifend"]
    system_requirement_keys: list[Text] = Field(min_length=1)
    depends_on: list[Text] = Field(default_factory=list)
    estimate_basis: Text
    assumptions: list[Text] = Field(default_factory=list)
    risks: list[Text] = Field(default_factory=list)

class Plan(Contract):
    work_packages: list[Package] = Field(min_length=1)

class Assessment(Contract):
    target_key: Text
    owner: Literal["requirements_engineer", "systems_engineer", "work_planner"]
    verdict: Literal["accepted", "accepted_with_assumptions", "changes_required", "blocked"]
    source_fidelity: Text
    necessity: Text
    completeness: Text
    feasibility: Text
    verifiability: Text
    sizing: Text
    question: str = ""
    required_change: str = ""

class Review(Contract):
    assessments: list[Assessment] = Field(default_factory=list)
    summary: Text
