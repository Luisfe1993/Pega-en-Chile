"""Tailor Agent.

Produces, for a given (Profile, JobPosting, optional CompanyBrief):
  - a `TailoredCV`: REORDER + REPHRASE existing bullets only, no fabrication
  - a `CoverLetter` in the same language as the job description (es | en)

Hard guardrails:
  1. The LLM is given the explicit list of existing bullets and told to
     attach each `rephrased` bullet to an `original` from that list.
  2. After generation, `validate_no_fabrication` checks that every
     `original` value matches a real bullet on the profile (fuzzy match).
     Any non-matching bullet is dropped, never silently kept.
"""

from __future__ import annotations

from difflib import SequenceMatcher

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from pega_agent.db import save_cover_letter, save_tailored_cv
from pega_agent.llm import get_chat_model
from pega_agent.models import (
    CompanyBrief,
    CoverLetter,
    JobPosting,
    Language,
    Profile,
    TailoredBullet,
    TailoredCV,
)


# ---------- helpers ------------------------------------------------------


def _all_bullets(profile: Profile) -> list[tuple[str, str]]:
    """Returns [(company, bullet)] across all experience items."""
    out: list[tuple[str, str]] = []
    for exp in profile.experience:
        for b in exp.bullets:
            out.append((exp.company, b))
    return out


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a.strip().lower(), b.strip().lower()).ratio()


def validate_no_fabrication(
    cv: TailoredCV, profile: Profile, *, threshold: float = 0.55
) -> TailoredCV:
    """Drop any bullet whose `original` doesn't fuzzy-match a real profile bullet."""
    real = _all_bullets(profile)
    kept: list[TailoredBullet] = []
    for b in cv.bullets:
        if any(b.company.lower() == c.lower() and _similar(b.original, t) >= threshold for c, t in real):
            kept.append(b)
    cv.bullets = kept
    return cv


def detect_jd_language(job: JobPosting) -> Language:
    """Cheap heuristic; the LLM also re-decides per-prompt."""
    text = (job.description + " " + job.title).lower()
    es_markers = (" del ", " los ", " las ", " que ", "experiencia", "buscamos", "gerente")
    if sum(m in text for m in es_markers) >= 2:
        return "es"
    return "en"


# ---------- LLM contracts ------------------------------------------------


class _TailorDraft(BaseModel):
    headline: str
    summary: str
    language: Language
    bullets: list[TailoredBullet] = Field(default_factory=list)
    skills_top: list[str] = Field(default_factory=list)
    notes: str | None = None


_TAILOR_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            (
                "You tailor a candidate's CV to a specific job posting for the\n"
                "Chilean market. STRICT RULES:\n"
                "  - You may REORDER and REPHRASE existing bullets only.\n"
                "  - You MUST NOT invent companies, titles, dates, metrics, tools or\n"
                "    achievements that are not in the provided bullet pool.\n"
                "  - Every output bullet must reference an `original` value that exists\n"
                "    verbatim (or near-verbatim) in the bullet pool, and the same `company`.\n"
                "  - `language` must match the dominant language of the job description.\n"
                "  - `headline` and `summary` are rephrased from the candidate's own\n"
                "    headline/summary; do not introduce new credentials.\n"
                "  - `skills_top`: pick 6-10 skills from the candidate's skills list that\n"
                "    appear (literally or as close synonyms) in the JD. Do not add new ones.\n"
                "  - Set `emphasis` 1-5 per bullet for ordering."
            ),
        ),
        (
            "user",
            (
                "Candidate name: {name}\n"
                "Candidate headline: {headline}\n"
                "Candidate summary: {summary}\n"
                "Candidate skills: {skills}\n\n"
                "Bullet pool (JSON list of {{company, bullet}}):\n{bullets}\n\n"
                "Job posting:\n"
                "  Title: {job_title}\n"
                "  Company: {job_company}\n"
                "  Description:\n```\n{job_description}\n```\n\n"
                "Company brief (optional): {brief}"
            ),
        ),
    ]
)


def tailor_cv(
    profile: Profile, job: JobPosting, brief: CompanyBrief | None = None
) -> TailoredCV:
    if not profile.experience:
        raise ValueError(
            "Profile has no experience items. Re-run `pega profile-from-pdf` "
            "with an LLM key set so bullets are populated."
        )
    model = get_chat_model(temperature=0.2)
    chain = _TAILOR_PROMPT | model.with_structured_output(_TailorDraft)
    pool = [{"company": c, "bullet": b} for c, b in _all_bullets(profile)]
    draft: _TailorDraft = chain.invoke(
        {
            "name": profile.name,
            "headline": profile.headline or "",
            "summary": profile.summary or "",
            "skills": ", ".join(profile.skills),
            "bullets": pool,
            "job_title": job.title,
            "job_company": job.company,
            "job_description": (job.description or "")[:4000],
            "brief": brief.what_they_do if brief else "(none)",
        }
    )
    cv = TailoredCV(
        job_id=job.id,
        language=draft.language,
        headline=draft.headline,
        summary=draft.summary,
        bullets=draft.bullets,
        skills_top=draft.skills_top,
        notes=draft.notes,
    )
    cv = validate_no_fabrication(cv, profile)
    save_tailored_cv(cv)
    return cv


# ---------- cover letter -------------------------------------------------


class _CoverDraft(BaseModel):
    subject: str | None = None
    body: str
    language: Language


_COVER_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            (
                "You draft a concise cover letter (180-260 words) for a Chilean-market\n"
                "job application. Rules:\n"
                "  - Use the same language as the job description.\n"
                "  - Reference 2-3 concrete bullets from the tailored CV's bullet list.\n"
                "  - Do NOT invent credentials. Use only facts from the CV.\n"
                "  - In Spanish, default to the formal 'usted' register unless the\n"
                "    company posting is clearly informal (startup, English-mixed copy).\n"
                "  - Open with one sentence that ties the candidate's track record to\n"
                "    a specific angle from the company brief (if provided).\n"
                "  - Close with a clear, low-pressure call to action."
            ),
        ),
        (
            "user",
            (
                "Candidate name: {name}\n"
                "Tailored CV (JSON): {cv}\n"
                "Job posting:\n  Title: {job_title}\n  Company: {job_company}\n"
                "  Description:\n```\n{job_description}\n```\n\n"
                "Company brief: {brief}"
            ),
        ),
    ]
)


def draft_cover_letter(
    profile: Profile,
    job: JobPosting,
    cv: TailoredCV,
    brief: CompanyBrief | None = None,
) -> CoverLetter:
    model = get_chat_model(temperature=0.4)
    chain = _COVER_PROMPT | model.with_structured_output(_CoverDraft)
    draft: _CoverDraft = chain.invoke(
        {
            "name": profile.name,
            "cv": cv.model_dump(),
            "job_title": job.title,
            "job_company": job.company,
            "job_description": (job.description or "")[:4000],
            "brief": brief.what_they_do if brief else "(none)",
        }
    )
    letter = CoverLetter(
        job_id=job.id,
        language=draft.language,
        subject=draft.subject,
        body=draft.body,
    )
    save_cover_letter(letter)
    return letter
