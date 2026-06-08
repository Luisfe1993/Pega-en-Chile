"""Profile Agent: parses a PDF/Markdown resume into a structured `Profile`."""

from __future__ import annotations

from pathlib import Path

import yaml
from pypdf import PdfReader

from pega_agent.models import Profile


def extract_pdf_text(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    return "\n".join((p.extract_text() or "") for p in reader.pages)


def bootstrap_profile_from_text(name: str, text: str) -> Profile:
    """Cheap heuristic seed. The LLM-backed pass refines this; see TODO."""
    return Profile(
        name=name,
        headline=None,
        target_roles=[],
        target_sectors=[],
        skills=[],
        summary=None,
        raw_text=text,
    )


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


# TODO(phase-1): add an LLM extractor that fills experience/education/skills
#                from `raw_text` and writes back into profile.yaml.
