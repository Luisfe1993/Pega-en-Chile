"""Profile Agent: parses a PDF/Markdown resume into a structured `Profile`.

Two paths:
- `bootstrap_profile_from_text` — heuristic seed (no API key needed)
- `extract_profile_with_llm`   — one-shot structured extraction via LLM
"""

from __future__ import annotations

from pathlib import Path

import yaml
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from pypdf import PdfReader

from pega_agent.llm import get_chat_model
from pega_agent.models import EducationItem, ExperienceItem, Profile, Seniority


def extract_pdf_text(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    return "\n".join((p.extract_text() or "") for p in reader.pages)


def bootstrap_profile_from_text(name: str, text: str) -> Profile:
    """Cheap heuristic seed used when no LLM key is configured."""
    return Profile(
        name=name,
        headline=None,
        target_roles=[],
        target_sectors=[],
        skills=[],
        summary=None,
        raw_text=text,
    )


# ---------- LLM-backed extraction ----------------------------------------


class _ExtractedProfile(BaseModel):
    """Subset of `Profile` fields the LLM is asked to fill in.

    Kept separate from `Profile` so the extractor can be conservative:
    if a field is uncertain, return None / [] rather than hallucinate.
    """

    headline: str | None = Field(
        default=None,
        description="One-line professional headline, e.g. 'Senior PM · AI · Energy'",
    )
    summary: str | None = Field(
        default=None,
        description="2-3 sentence career summary in the resume's language",
    )
    skills: list[str] = Field(
        default_factory=list,
        description="Concrete hard skills, tools, frameworks. Lowercase. No soft skills.",
    )
    target_roles: list[str] = Field(
        default_factory=list,
        description="4-6 plausible target titles in Spanish AND English",
    )
    target_sectors: list[str] = Field(
        default_factory=list,
        description="3-5 sectors inferred from past employers",
    )
    target_seniority: Seniority = Field(default="manager")
    experience: list[ExperienceItem] = Field(default_factory=list)
    education: list[EducationItem] = Field(default_factory=list)


_EXTRACTOR_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            (
                "You extract structured candidate profiles from raw resume text.\n"
                "Rules:\n"
                "  - Do NOT invent experience, dates, companies, schools or credentials.\n"
                "  - Preserve the resume's original language for `headline` and `summary`.\n"
                "  - `target_roles`: 4-6 plausible titles mixing Spanish AND English variants\n"
                "    relevant to the Chilean market.\n"
                "  - `target_sectors`: infer 3-5 sectors from past employers.\n"
                "  - `target_seniority`: PM/Sr PM → manager; Director → director; etc.\n"
                "  - `skills`: hard skills only (tools, methods, domains). No soft skills.\n"
                "  - If a date is unknown, leave it null. Do not guess."
            ),
        ),
        ("user", "Resume text:\n\n```\n{resume_text}\n```"),
    ]
)


def extract_profile_with_llm(name: str, text: str) -> Profile:
    """One-shot structured extraction. Requires an LLM API key."""
    model = get_chat_model(temperature=0.0)
    chain = _EXTRACTOR_PROMPT | model.with_structured_output(_ExtractedProfile)
    extracted: _ExtractedProfile = chain.invoke({"resume_text": text})
    return Profile(
        name=name,
        headline=extracted.headline,
        summary=extracted.summary,
        skills=extracted.skills,
        target_roles=extracted.target_roles,
        target_sectors=extracted.target_sectors,
        target_seniority=extracted.target_seniority,
        experience=extracted.experience,
        education=extracted.education,
        raw_text=text,
    )


# ---------- IO ------------------------------------------------------------


def load_profile(path: Path) -> Profile:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return Profile(**data)


def save_profile(profile: Profile, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            profile.model_dump(exclude_none=True), sort_keys=False, allow_unicode=True
        ),
        encoding="utf-8",
    )
