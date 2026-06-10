"""Recruiter intro drafter.

Generates a concise, bilingual (ES + EN) outreach message to a head-hunter
or search-firm consultant for a SPECIFIC opening at a SPECIFIC company.

Strategy (from Round 4 of the search-tuning interview):
- Reactive only — call this when a real opening at a watchlist company surfaces.
- Tone: confident, respectful of recruiter's time.
- Hook: one sentence tying the candidate's track record to the opening's
  specific challenge.
- Ask: low-pressure 20-min call.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from pega_agent.db import save_recruiter_intro
from pega_agent.llm import get_chat_model
from pega_agent.models import CompanyBrief, JobPosting, Profile, RecruiterIntro


class _IntroDraft(BaseModel):
    subject_es: str
    body_es: str
    subject_en: str
    body_en: str
    rationale: str | None = Field(default=None)


_RECRUITER_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            (
                "You draft a concise outreach message from a senior product leader\n"
                "to a head-hunter / executive-search consultant about a SPECIFIC opening.\n\n"
                "Produce BOTH Spanish (formal 'usted') AND English versions of subject+body.\n\n"
                "Hard rules:\n"
                "  - 110-160 words per body. No filler.\n"
                "  - Write in FIRST PERSON as the candidate (yo / I). Never refer to\n"
                "    the candidate in the third person ('Luis Felipe drove...', 'he led...').\n"
                "    The message is sent BY the candidate, even when the recruiter is a\n"
                "    warm contact who already knows them.\n"
                "  - Open by referencing the specific opening (title + company).\n"
                "  - Hook in sentence 2: tie one concrete achievement from the candidate's\n"
                "    profile to a specific challenge implied by the role.\n"
                "  - Mention 1-2 numeric proof points from the candidate's bullets.\n"
                "  - Close with a low-pressure ask: a 20-minute call.\n"
                "  - Sign off with the candidate's name on its own line.\n"
                "  - Spanish: formal 'usted' register unless the firm is clearly informal.\n"
                "  - English: direct, no buzzwords ('synergy', 'leverage', 'passionate').\n"
                "  - Do NOT fabricate achievements not in the candidate bullets.\n"
                "  - Do NOT claim availability dates.\n"
                "  - Subject line: <=70 chars, no emojis. Do NOT repeat the subject inside\n"
                "    the body.\n"
                "  - If `contact_name` is provided, address them by first name; else use\n"
                "    a respectful generic ('Estimado equipo de {firm}' / 'Hello {firm} team').\n"
            ),
        ),
        (
            "user",
            (
                "Candidate: {name} ({headline})\n"
                "Candidate summary: {summary}\n"
                "Candidate bullet pool (use only these as proof points):\n{bullets}\n\n"
                "Recruiting firm: {firm}\n"
                "Contact (may be empty): {contact_name}\n"
                "Firm tier/notes: {firm_notes}\n\n"
                "Opening:\n"
                "  Title: {job_title}\n"
                "  Company: {job_company}\n"
                "  Location: {job_location}\n"
                "  Description excerpt:\n```\n{job_description}\n```\n\n"
                "Company brief (may be empty): {brief}\n"
            ),
        ),
    ]
)


def _flatten_bullets(profile: Profile, max_n: int = 18) -> str:
    rows: list[str] = []
    for exp in profile.experience:
        for b in exp.bullets:
            rows.append(f"- [{exp.company}] {b}")
            if len(rows) >= max_n:
                return "\n".join(rows)
    return "\n".join(rows)


def load_recruiters_yaml(path: Path) -> dict:
    if not path.exists():
        return {"warm_contacts": [], "target_firms": [], "rules": {}}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def resolve_firm_notes(recruiters_data: dict, firm: str) -> str:
    """Return tier/keywords or warm-contact notes for the named firm."""
    firm_l = firm.lower().strip()
    for f in recruiters_data.get("target_firms", []) or []:
        if (f.get("name") or "").lower() == firm_l:
            tier = f.get("tier", "unknown")
            kws = ", ".join(f.get("track_keywords", []) or [])
            return f"tier={tier}; track_keywords=[{kws}]"
    for w in recruiters_data.get("warm_contacts", []) or []:
        if (w.get("firm") or "").lower() == firm_l or (
            w.get("name") or ""
        ).lower() == firm_l:
            notes = (w.get("notes") or "").strip().replace("\n", " ")
            return f"warm contact: {notes}"
    return "no prior notes"


def draft_recruiter_intro(
    profile: Profile,
    job: JobPosting,
    firm: str,
    *,
    contact_name: str | None = None,
    brief: CompanyBrief | None = None,
    recruiters_data: dict | None = None,
) -> RecruiterIntro:
    """Generate a bilingual recruiter intro and persist it."""
    if not profile.experience:
        raise ValueError("Profile has no experience bullets to anchor the intro.")
    model = get_chat_model(temperature=0.3)
    chain = _RECRUITER_PROMPT | model.with_structured_output(_IntroDraft)
    firm_notes = (
        resolve_firm_notes(recruiters_data, firm) if recruiters_data else "no prior notes"
    )
    draft: _IntroDraft = chain.invoke(
        {
            "name": profile.name,
            "headline": profile.headline or "",
            "summary": profile.summary or "",
            "bullets": _flatten_bullets(profile),
            "firm": firm,
            "contact_name": contact_name or "",
            "firm_notes": firm_notes,
            "job_title": job.title,
            "job_company": job.company,
            "job_location": job.location or "",
            "job_description": (job.description or "")[:3000],
            "brief": brief.what_they_do if brief else "(none)",
        }
    )
    intro = RecruiterIntro(
        job_id=job.id,
        firm=firm,
        contact_name=contact_name,
        subject_es=draft.subject_es,
        body_es=draft.body_es,
        subject_en=draft.subject_en,
        body_en=draft.body_en,
        rationale=draft.rationale,
    )
    save_recruiter_intro(intro)
    return intro
