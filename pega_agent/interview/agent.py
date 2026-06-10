"""Interview Prep Agent.

Generates a per-job `InterviewPrepPack` for an approved job:
  - 4-6 STAR stories, each grounded in a real CV bullet
  - 1-2 PM case warmups tailored to the company's actual product
  - 5 questions to ask, grounded in recent news / brief
  - 6-8 likely behavioral / PM-functional questions

Same no-fabrication rule as the Tailor agent: every STAR story must trace
back to a (company, bullet) pair on the candidate's profile.
"""

from __future__ import annotations

from difflib import SequenceMatcher

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from pega_agent.db import save_interview_prep
from pega_agent.llm import get_chat_model
from pega_agent.models import (
    CaseWarmup,
    CompanyBrief,
    InterviewPrepPack,
    JobPosting,
    Language,
    Profile,
    STARStory,
    TailoredCV,
)


def _all_bullets(profile: Profile) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for exp in profile.experience:
        for b in exp.bullets:
            out.append((exp.company, b))
    return out


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a.strip().lower(), b.strip().lower()).ratio()


def validate_stars(stories: list[STARStory], profile: Profile, *, threshold: float = 0.55) -> list[STARStory]:
    """Drop stories whose source bullet doesn't trace back to the profile."""
    real = _all_bullets(profile)
    kept: list[STARStory] = []
    for s in stories:
        if any(s.source_company.lower() == c.lower() and _similar(s.source_bullet, t) >= threshold for c, t in real):
            kept.append(s)
    return kept


# ---------- LLM contracts ------------------------------------------------


class _PrepDraft(BaseModel):
    language: Language
    company_angle: str = Field(
        description="One paragraph: why this company is interesting NOW, grounded in the brief."
    )
    star_stories: list[STARStory] = Field(default_factory=list)
    case_warmups: list[CaseWarmup] = Field(default_factory=list)
    questions_to_ask: list[str] = Field(
        default_factory=list, description="5 questions, grounded in recent news / strategy"
    )
    likely_questions: list[str] = Field(
        default_factory=list, description="6-8 likely behavioral + PM-functional questions"
    )


_PREP_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            (
                "You are a senior product-management interview coach producing a tight\n"
                "prep pack for a candidate interviewing in the Chilean market.\n"
                "Rules:\n"
                "  - STRICT: every STAR story must reference a (company, bullet) that\n"
                "    exists verbatim in the bullet pool. Do NOT invent metrics or events.\n"
                "  - Use 'language' that matches the job description (es | en).\n"
                "  - Produce 4-6 STAR stories covering distinct themes (leadership,\n"
                "    ownership, ambiguity, conflict, failure, impact, 0-to-1).\n"
                "  - 1-2 case warmups that are SPECIFIC to the company's actual product.\n"
                "    No generic 'how would you grow Facebook' prompts.\n"
                "  - `questions_to_ask`: 5 questions a senior candidate would credibly ask,\n"
                "    each tied to recent news, strategy or a known org change.\n"
                "  - `likely_questions`: cover behavioral + PM-functional (prioritization,\n"
                "    metrics, roadmap, stakeholder management, technical literacy).\n"
                "  - `company_angle`: tie the candidate's track record to the company's\n"
                "    moment. No fluff. No 'I'm a passionate professional'."
            ),
        ),
        (
            "user",
            (
                "Candidate: {name} — {headline}\n"
                "Candidate summary: {summary}\n"
                "Bullet pool (JSON [{{company, bullet}}]):\n{bullets}\n\n"
                "Job posting:\n"
                "  Title: {job_title}\n"
                "  Company: {job_company}\n"
                "  Description:\n```\n{job_description}\n```\n\n"
                "Company brief: {brief}\n"
                "Tailored CV (optional): {cv}"
            ),
        ),
    ]
)


def generate_prep_pack(
    profile: Profile,
    job: JobPosting,
    brief: CompanyBrief | None = None,
    cv: TailoredCV | None = None,
) -> InterviewPrepPack:
    if not profile.experience:
        raise ValueError(
            "Profile has no experience items. Re-run `pega profile-from-pdf` with an LLM key set."
        )
    model = get_chat_model(temperature=0.3)
    chain = _PREP_PROMPT | model.with_structured_output(_PrepDraft)
    pool = [{"company": c, "bullet": b} for c, b in _all_bullets(profile)]
    draft: _PrepDraft = chain.invoke(
        {
            "name": profile.name,
            "headline": profile.headline or "",
            "summary": profile.summary or "",
            "bullets": pool,
            "job_title": job.title,
            "job_company": job.company,
            "job_description": (job.description or "")[:4000],
            "brief": (brief.what_they_do if brief else "(none)"),
            "cv": (cv.model_dump() if cv else "(none)"),
        }
    )
    stars = validate_stars(draft.star_stories, profile)
    pack = InterviewPrepPack(
        job_id=job.id,
        language=draft.language,
        company_angle=draft.company_angle,
        star_stories=stars,
        case_warmups=draft.case_warmups,
        questions_to_ask=draft.questions_to_ask,
        likely_questions=draft.likely_questions,
    )
    save_interview_prep(pack)
    return pack
