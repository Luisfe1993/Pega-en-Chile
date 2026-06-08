"""Outreach Agent.

Given a `JobPosting` (+ optional `CompanyBrief`, `TailoredCV`), drafts an
`OutreachDraft` that the human will review.

Pathing strategy (see skills/network-graph/SKILL.md):
  1. Direct contact at the target company    → warm intro / DM
  2. Sector-tagged contact                   → informational chat
  3. Headhunter-tagged contact (Director+)   → executive-search ping
  4. Nothing useful                          → cold DM, no false claims of
                                                a mutual connection
"""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from pega_agent.db import save_outreach
from pega_agent.llm import get_chat_model
from pega_agent.models import (
    CompanyBrief,
    JobPosting,
    NetworkContact,
    OutreachChannel,
    OutreachDraft,
    Profile,
    Register,
    ReferralPath,
    TailoredCV,
)
from pega_agent.network.loader import find_paths_by_sector, find_paths_to_company


def choose_referral(
    job: JobPosting,
    contacts: list[NetworkContact],
    *,
    brief: CompanyBrief | None = None,
    seniority: str = "manager",
) -> tuple[NetworkContact | None, OutreachChannel, Register]:
    """Returns (best_contact, channel, register)."""
    direct = find_paths_to_company(job.company, contacts)
    if direct:
        c = direct[0]
        return c, "warm_intro_request", c.register

    sector = (brief.sector if brief else None) or ""
    if sector:
        sector_match = find_paths_by_sector(sector, contacts)
        if sector_match:
            c = sector_match[0]
            return c, "linkedin_dm", c.register

    if seniority in {"director", "vp", "c-level"}:
        hh = [c for c in contacts if any(t in {"headhunter", "executive-search"} for t in c.tags)]
        if hh:
            hh.sort(key=lambda x: x.strength, reverse=True)
            return hh[0], "linkedin_dm", hh[0].register

    return None, "linkedin_dm", "es-usted"


# ---------- LLM contract --------------------------------------------------


class _OutreachDraftLLM(BaseModel):
    subject: str | None = None
    body: str = Field(description="Plain text. ~120-180 words. No markdown.")


def _system_prompt_for(register: Register, channel: OutreachChannel) -> str:
    register_rules = {
        "es-usted": "Spanish, formal 'usted' register. Neutral Chilean Spanish.",
        "es-tu": "Spanish, informal 'tú' register. Neutral Chilean Spanish.",
        "en": "English. Direct, professional, lightly warm.",
    }[register]

    channel_rules = {
        "linkedin_dm": "LinkedIn DM (max ~180 words). No subject. No greeting fluff.",
        "email": "Short email. Include a concise subject line.",
        "warm_intro_request": (
            "Message to a mutual connection asking for an introduction. "
            "Make it forwardable: include a 2-3 line blurb they can paste."
        ),
    }[channel]

    return (
        f"You draft outreach for a Chilean-market job search.\n"
        f"Channel: {channel_rules}\n"
        f"Language/register: {register_rules}\n"
        "Hard rules:\n"
        "  - Never claim a relationship that wasn't provided.\n"
        "  - Never invent metrics or credentials. Only use what's in the CV / brief.\n"
        "  - One clear ask, no multi-asks.\n"
        "  - Low-pressure close ('si tiene 15 min…' / 'if you have 15 min…').\n"
        "  - No emojis. No hashtags. No 'I hope this finds you well.'\n"
    )


def draft_outreach(
    profile: Profile,
    job: JobPosting,
    contacts: list[NetworkContact],
    *,
    brief: CompanyBrief | None = None,
    cv: TailoredCV | None = None,
) -> OutreachDraft:
    contact, channel, register = choose_referral(
        job, contacts, brief=brief, seniority=profile.target_seniority
    )

    referral = None
    if contact:
        referral = ReferralPath(
            target_company=job.company,
            contact_name=contact.name,
            relationship=contact.relationship,
            rationale=(
                f"Direct contact at {contact.company}"
                if contact.company and job.company.lower() in (contact.company or "").lower()
                else f"Tagged with relevant sector / circle: {', '.join(contact.tags)}"
            ),
            confidence=min(1.0, contact.strength / 5),
        )

    model = get_chat_model(temperature=0.35)
    system = _system_prompt_for(register, channel)
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system),
            (
                "user",
                "Candidate: {name} — {headline}\n"
                "Tailored CV summary: {cv_summary}\n"
                "Job: {job_title} @ {job_company}\n"
                "Company angle: {brief}\n"
                "Recipient: {recipient}\n"
                "Relationship: {relationship}\n"
                "Recipient role: {recipient_role}\n",
            ),
        ]
    )
    chain = prompt | model.with_structured_output(_OutreachDraftLLM)
    draft: _OutreachDraftLLM = chain.invoke(
        {
            "name": profile.name,
            "headline": profile.headline or "",
            "cv_summary": (cv.summary if cv else profile.summary) or "",
            "job_title": job.title,
            "job_company": job.company,
            "brief": brief.what_they_do if brief else "(none)",
            "recipient": (contact.name if contact else "Hiring Manager / Recruiter"),
            "relationship": (contact.relationship if contact else "(none — cold message)"),
            "recipient_role": (contact.role if contact else "(unknown)"),
        }
    )

    out = OutreachDraft(
        job_id=job.id,
        channel=channel,
        recipient_name=contact.name if contact else None,
        recipient_company=contact.company if contact else job.company,
        register=register,
        subject=draft.subject,
        body=draft.body,
        referral_path=referral,
    )
    save_outreach(out)
    return out
