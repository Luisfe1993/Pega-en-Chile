"""Negotiation Agent.

Given (Profile, JobPosting, current offer in CLP), produces a `NegotiationDraft`:
  - CLP/USD benchmark for the role+seniority+sector (LLM-inferred against the
    comp-bands-chile skill; user should sanity-check)
  - Recommended target base, walk-away floor, and rationale
  - Levers beyond base: bono, vacaciones, gratificación cap, sign-on,
    equity (rare in CL), scope/title, remoto
  - Counter-offer email draft (es-usted by default)

Sanity rails:
  - If the offer is >= 90% of inferred high-band, target is +5-10% only.
  - If the offer is < benchmark low-band, the agent flags it and proposes
    a 20-30% counter with explicit rationale.
  - Walk-away floor never drops below the user-supplied `min_clp` if provided.
"""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from pega_agent.db import save_negotiation
from pega_agent.llm import get_chat_model
from pega_agent.models import (
    CompanyBrief,
    CompBenchmark,
    JobPosting,
    Language,
    NegotiationDraft,
    Profile,
)


class _NegotiationDraftLLM(BaseModel):
    benchmark: CompBenchmark
    target_base_clp: int = Field(description="Recommended ask, gross monthly CLP")
    walk_away_clp: int = Field(description="Floor below which the candidate should walk")
    levers_to_negotiate: list[str] = Field(default_factory=list)
    rationale: str = Field(description="Why this target; reference benchmark + market + leverage")
    counter_email_subject: str | None = None
    counter_email_body: str
    language: Language = "es"


_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            (
                "You are a compensation-negotiation coach specialized in the Chilean\n"
                "market. Produce a tight, evidence-based counter-offer plan.\n"
                "Rules:\n"
                "  - CLP figures are GROSS MONTHLY unless explicitly noted.\n"
                "  - Benchmark ranges should reflect Chilean reality for the given role,\n"
                "    seniority and sector. If uncertain, widen the range and say so in `notes`.\n"
                "  - If the offer is >= 90% of benchmark high, recommend a modest 5-10% ask;\n"
                "    don't push for double-digit jumps with no leverage.\n"
                "  - If the offer is below benchmark low, recommend a 20-30% counter with\n"
                "    explicit rationale.\n"
                "  - Always list levers beyond base: bono variable, gratificación cap (4.75x),\n"
                "    vacaciones adicionales, sign-on, equity (rare in CL — flag it), scope/title,\n"
                "    remoto/híbrido, fecha de inicio.\n"
                "  - The counter email defaults to Spanish formal (usted), neutral CL register.\n"
                "    Switch to English only if the job description was in English.\n"
                "  - Never claim a competing offer if `competing_offer_clp` is null.\n"
                "  - Walk-away floor must respect `min_clp` if provided."
            ),
        ),
        (
            "user",
            (
                "Candidate: {name} — {headline}\n"
                "Seniority target: {seniority}\n"
                "Target sectors: {sectors}\n"
                "Min acceptable comp (CLP gross/mo): {min_clp}\n\n"
                "Job:\n  Title: {job_title}\n  Company: {job_company}\n"
                "  Description:\n```\n{job_description}\n```\n\n"
                "Company brief: {brief}\n\n"
                "Current offer (CLP gross/mo base): {offer_base_clp}\n"
                "Current offer variable (% of base): {offer_variable_pct}\n"
                "Competing offer (CLP gross/mo, if any): {competing_offer_clp}\n"
            ),
        ),
    ]
)


def negotiate(
    profile: Profile,
    job: JobPosting,
    offer_base_clp: int,
    *,
    offer_variable_pct: float | None = None,
    competing_offer_clp: int | None = None,
    brief: CompanyBrief | None = None,
) -> NegotiationDraft:
    model = get_chat_model(temperature=0.2)
    chain = _PROMPT | model.with_structured_output(_NegotiationDraftLLM)
    draft: _NegotiationDraftLLM = chain.invoke(
        {
            "name": profile.name,
            "headline": profile.headline or "",
            "seniority": profile.target_seniority,
            "sectors": ", ".join(profile.target_sectors),
            "min_clp": profile.target_min_comp_clp or "(unspecified)",
            "job_title": job.title,
            "job_company": job.company,
            "job_description": (job.description or "")[:3000],
            "brief": (brief.what_they_do if brief else "(none)"),
            "offer_base_clp": offer_base_clp,
            "offer_variable_pct": offer_variable_pct if offer_variable_pct is not None else "(unspecified)",
            "competing_offer_clp": competing_offer_clp if competing_offer_clp is not None else "(none)",
        }
    )

    # Enforce the min-CLP guardrail in code, not just in the prompt
    walk_away = draft.walk_away_clp
    if profile.target_min_comp_clp:
        walk_away = max(walk_away, profile.target_min_comp_clp)

    neg = NegotiationDraft(
        job_id=job.id,
        offer_base_clp=offer_base_clp,
        offer_variable_pct=offer_variable_pct,
        competing_offer_clp=competing_offer_clp,
        target_base_clp=draft.target_base_clp,
        walk_away_clp=walk_away,
        benchmark=draft.benchmark,
        levers_to_negotiate=draft.levers_to_negotiate,
        rationale=draft.rationale,
        counter_email_subject=draft.counter_email_subject,
        counter_email_body=draft.counter_email_body,
        language=draft.language,
    )
    save_negotiation(neg)
    return neg
