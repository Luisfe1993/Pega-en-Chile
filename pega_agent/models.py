from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Seniority = Literal[
    "intern", "junior", "mid", "senior", "lead", "manager", "director", "vp", "c-level"
]


class ExperienceItem(BaseModel):
    company: str
    title: str
    location: str | None = None
    start: str
    end: str | None = None  # None = present
    bullets: list[str] = Field(default_factory=list)
    sectors: list[str] = Field(default_factory=list)


class EducationItem(BaseModel):
    school: str
    degree: str
    field: str | None = None
    year: int | None = None
    honors: list[str] = Field(default_factory=list)


class Profile(BaseModel):
    """Candidate profile. Single source of truth for tailoring + matching."""

    name: str
    headline: str | None = None
    locations_open_to: list[str] = Field(default_factory=lambda: ["Santiago, CL"])
    work_authorization: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=lambda: ["es", "en"])

    target_roles: list[str] = Field(default_factory=list)
    target_seniority: Seniority = "manager"
    target_sectors: list[str] = Field(default_factory=list)
    target_min_comp_clp: int | None = None  # gross monthly CLP

    skills: list[str] = Field(default_factory=list)
    experience: list[ExperienceItem] = Field(default_factory=list)
    education: list[EducationItem] = Field(default_factory=list)

    summary: str | None = None
    raw_text: str | None = None  # original CV text for reference


class JobPosting(BaseModel):
    id: str  # hash(source + url)
    source: str  # 'linkedin' | 'getonboard' | 'laborum' | ...
    url: str
    title: str
    company: str
    location: str | None = None
    remote: bool | None = None
    seniority: str | None = None
    posted_at: datetime | None = None
    description: str = ""
    salary_min_clp: int | None = None
    salary_max_clp: int | None = None
    salary_currency: str | None = None
    raw: dict = Field(default_factory=dict)


class MatchScore(BaseModel):
    job_id: str
    score: float  # 0..100
    rationale: str
    skill_overlap: float = 0.0
    seniority_fit: float = 0.0
    sector_fit: float = 0.0
    location_fit: float = 0.0
    comp_fit: float | None = None
