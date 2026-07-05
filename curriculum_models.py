from __future__ import annotations

from typing import List
from pydantic import BaseModel, Field


class MediumWeek(BaseModel):
    content: str = Field(description="Concise unit and lesson content for this week")
    learning_objectives: str = Field(description="Two measurable learning objectives, concise")
    ai_literacy: str = Field(description="One safe and purposeful AI literacy integration objective")
    resources: str = Field(description="Concise list of learning resources and approved AI tools")


class ComplianceItem(BaseModel):
    area: str
    milestone: str
    responsible_person: str
    target_date: str
    status: str


class MediumPlan(BaseModel):
    title: str
    targets: str
    weeks: List[MediumWeek]
    assessment_opportunities: str
    century_skills: str
    vocabulary: str
    eps_guiding_statement: str
    global_citizenship: str
    cross_curricular: str
    national_identity: str
    ai_integration_approach: str
    guardrails_prompt_controls: str
    cognitive_integrity_strategy: str
    ai_safeguarding: str
    compliance: List[ComplianceItem]


class HalfTerm(BaseModel):
    title: str
    content: str = Field(description="Units and main topics for the half-term, concise bullet-ready text")
    summative_assessment: str


class LongPlan(BaseModel):
    half_terms: List[HalfTerm]
    compliance: List[ComplianceItem]
