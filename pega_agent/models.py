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
    semantic_fit: float = 0.0
    comp_fit: float | None = None


class CompanyBrief(BaseModel):
    """Concise enrichment for a target company, produced by the Research agent."""

    company: str
    what_they_do: str
    sector: str | None = None
    size: str | None = None  # 'startup' | 'scale-up' | 'enterprise' | etc.
    headquarters: str | None = None
    recent_news: list[str] = Field(default_factory=list)
    why_role_exists: str | None = None
    red_flags: list[str] = Field(default_factory=list)
    talking_points: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=datetime.utcnow)


# ---------- Phase 4: Tailor / Network / Outreach / Approval ---------------

Language = Literal["es", "en"]
Register = Literal["es-usted", "es-tu", "en"]


class TailoredBullet(BaseModel):
    """A single resume bullet, possibly reordered or rephrased.

    `original` MUST match an existing bullet on the profile. `rephrased`
    is the version that goes into the tailored CV. Set `emphasis` to a
    1-5 score the Tailor agent uses to reorder within a role.
    """

    company: str
    original: str
    rephrased: str
    emphasis: int = 3
    rationale: str | None = None


class TailoredCV(BaseModel):
    """Per-job tailored CV — reorder + rephrase only. No fabrication."""

    job_id: str
    language: Language = "en"
    headline: str
    summary: str
    bullets: list[TailoredBullet] = Field(default_factory=list)
    skills_top: list[str] = Field(default_factory=list)
    notes: str | None = None
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class CoverLetter(BaseModel):
    job_id: str
    language: Language
    recipient: str | None = None  # 'Hiring Manager' fallback
    subject: str | None = None
    body: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class NetworkContact(BaseModel):
    """One person in your warm network."""

    name: str
    company: str | None = None
    role: str | None = None
    relationship: str | None = None  # 'UC Ingeniería classmate', 'ex-Copec', etc.
    strength: int = Field(default=3, ge=1, le=5)  # 1=cold, 5=close
    register: Register = "es-tu"
    linkedin_url: str | None = None
    email: str | None = None
    last_contacted: datetime | None = None
    notes: str | None = None
    tags: list[str] = Field(default_factory=list)


class ReferralPath(BaseModel):
    """A suggested warm-intro path to a target company."""

    target_company: str
    contact_name: str
    relationship: str | None = None
    rationale: str
    confidence: float = 0.0  # 0..1


OutreachChannel = Literal["linkedin_dm", "email", "warm_intro_request"]


class OutreachDraft(BaseModel):
    job_id: str
    channel: OutreachChannel
    recipient_name: str | None = None
    recipient_company: str | None = None
    register: Register = "es-usted"
    subject: str | None = None
    body: str
    referral_path: ReferralPath | None = None
    generated_at: datetime = Field(default_factory=datetime.utcnow)


ApprovalStatus = Literal["pending", "approved", "rejected", "edited"]


class ApprovalDecision(BaseModel):
    """Records the human decision on a draft at the Quality Gate."""

    job_id: str
    artifact: Literal["tailored_cv", "cover_letter", "outreach"]
    status: ApprovalStatus = "pending"
    edited_body: str | None = None
    reviewer_note: str | None = None
    decided_at: datetime = Field(default_factory=datetime.utcnow)
