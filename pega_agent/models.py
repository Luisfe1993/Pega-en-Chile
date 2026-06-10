from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Seniority = Literal[
    "intern", "junior", "mid", "senior", "lead", "manager", "director", "vp", "c-level"
]

CompanySize = Literal["large", "mid", "small"]
WorkModel = Literal["remote", "hybrid", "onsite"]
PeopleMgmt = Literal["required", "preferred", "neutral", "avoid"]


class CompanySizeTarget(BaseModel):
    """Per-company-size band: what role levels you want there."""

    size: CompanySize
    target_levels: list[Seniority] = Field(default_factory=list)


class SearchWeights(BaseModel):
    """Soft-signal weights. Must sum to ~1.0; matcher renormalizes."""

    semantic: float = 0.25
    seniority: float = 0.20
    skills: float = 0.10
    people_mgmt: float = 0.15
    company_size: float = 0.15
    location: float = 0.05
    compensation: float = 0.10
    international_exposure: float = 0.0  # boost roles with multi-country / global scope


class Search(BaseModel):
    """What the user wants. Separate from Profile (who they are).

    Hard filters drop a job before scoring; soft signals shape the score.
    """

    # ---- Hard filters (failing any → job is dropped) ----
    locations: list[str] = Field(default_factory=lambda: ["Santiago, CL", "Remote"])
    min_comp_clp: int | None = None
    excluded_titles: list[str] = Field(default_factory=list)
    excluded_industries: list[str] = Field(default_factory=list)
    dealbreaker_keywords: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=lambda: ["es", "en"])

    # ---- Soft signals ----
    queries: list[str] = Field(default_factory=lambda: ["product manager"])
    target_titles: list[str] = Field(default_factory=list)
    company_size_targets: list[CompanySizeTarget] = Field(default_factory=list)
    preferred_industries: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    nice_to_have_skills: list[str] = Field(default_factory=list)
    people_management: PeopleMgmt = "preferred"
    work_model: list[WorkModel] = Field(default_factory=lambda: ["remote", "hybrid", "onsite"])

    # ---- Run config ----
    max_results_per_query: int = 60
    weights: SearchWeights = Field(default_factory=SearchWeights)

    # Static list of known large CL companies, used as a default size detector
    # when the Research agent hasn't enriched the company yet.
    known_large_companies: list[str] = Field(
        default_factory=lambda: [
            "falabella", "cencosud", "ripley", "lider", "walmart", "copec", "enel",
            "entel", "movistar", "wom", "claro", "scotiabank", "santander", "bci",
            "banco de chile", "banco estado", "lan", "latam", "codelco", "antofagasta",
            "soquimich", "sqm", "arauco", "cmpc", "concha y toro", "salfacorp",
            "mercadolibre", "rappi", "uber", "globant", "ey", "deloitte", "kpmg",
            "pwc", "accenture", "mckinsey", "bain", "bcg", "microsoft", "google",
            "amazon", "ibm", "oracle", "sap", "tcs", "infosys", "wipro",
        ]
    )


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


# ---------- Phase 5: Interview Prep / Negotiation ------------------------

BehavioralTheme = Literal[
    "leadership",
    "ownership",
    "ambiguity",
    "conflict",
    "failure",
    "impact",
    "stakeholder",
    "data-driven-decision",
    "speed-vs-quality",
    "0-to-1",
]


class STARStory(BaseModel):
    """A behavioral-interview story grounded in a real CV bullet."""

    theme: BehavioralTheme
    title: str
    situation: str
    task: str
    action: str
    result: str
    source_company: str
    source_bullet: str  # the original bullet this story derives from
    language: Language = "en"


class CaseWarmup(BaseModel):
    """A short PM case scenario tailored to the company's product."""

    prompt: str
    suggested_framework: str
    key_dimensions: list[str] = Field(default_factory=list)
    likely_followups: list[str] = Field(default_factory=list)
    language: Language = "en"


class InterviewPrepPack(BaseModel):
    """Per-job prep pack. Generated on demand for approved jobs only."""

    job_id: str
    language: Language = "en"
    company_angle: str  # one-paragraph why-this-company-now
    star_stories: list[STARStory] = Field(default_factory=list)
    case_warmups: list[CaseWarmup] = Field(default_factory=list)
    questions_to_ask: list[str] = Field(default_factory=list)
    likely_questions: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class CompBenchmark(BaseModel):
    """Compensation benchmark for a role+seniority in Chile (CLP gross/mo)."""

    role: str
    seniority: Seniority
    sector: str | None = None
    base_low_clp: int
    base_mid_clp: int
    base_high_clp: int
    variable_pct: float = 0.0  # bonus as % of base, typical
    notes: str | None = None
    sources: list[str] = Field(default_factory=list)


class NegotiationDraft(BaseModel):
    """A negotiation plan + counter-offer draft for an approved job."""

    job_id: str
    offer_base_clp: int
    offer_variable_pct: float | None = None
    competing_offer_clp: int | None = None
    target_base_clp: int  # what the agent recommends asking for
    walk_away_clp: int  # floor
    benchmark: CompBenchmark | None = None
    levers_to_negotiate: list[str] = Field(default_factory=list)  # bono, vacaciones, equity, sign-on, scope, title
    rationale: str
    counter_email_subject: str | None = None
    counter_email_body: str  # es-usted by default
    language: Language = "es"
    generated_at: datetime = Field(default_factory=datetime.utcnow)


# ---------- Phase 6: Recruiter outreach + log ----------------------------


class RecruiterIntro(BaseModel):
    """Bilingual intro message to a head-hunter / search-firm consultant.

    Generated on-demand by `pega recruiter-intro <job_id>`. The user copies
    the relevant version (es or en) into LinkedIn/email. Stored in DB so we
    don't pay for the same LLM call twice.
    """

    job_id: str
    firm: str  # 'Spencer Stuart' | 'Korn Ferry' | 'Manuel Honorato (warm)' | ...
    contact_name: str | None = None  # if known
    subject_es: str
    body_es: str
    subject_en: str
    body_en: str
    rationale: str | None = None  # what the LLM keyed on
    generated_at: datetime = Field(default_factory=datetime.utcnow)


OutreachLogStatus = Literal[
    "drafted", "sent", "replied", "call_booked", "rejected", "ghosted"
]
OutreachLogChannel = Literal["linkedin", "email", "phone", "warm_intro", "other"]


class OutreachLogEntry(BaseModel):
    """One outbound touch on a recruiter / hiring manager / warm contact.

    Distinct from `OutreachDraft` (which is the agent-drafted message
    awaiting approval at the Quality Gate). This is the manual tracker:
    "I sent message X on date Y, got reply Z on date W".
    """

    id: str  # short uuid
    contact_name: str
    firm: str | None = None
    job_id: str | None = None  # link to the opening that triggered it
    channel: OutreachLogChannel = "linkedin"
    status: OutreachLogStatus = "drafted"
    sent_at: datetime | None = None
    replied_at: datetime | None = None
    follow_up_at: datetime | None = None  # reminder date
    notes: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
