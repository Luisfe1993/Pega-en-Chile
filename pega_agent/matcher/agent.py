"""Matcher Agent: scores each job 0..100 against the candidate profile.

MVP scoring blends:
  - keyword overlap (skills ∩ description)         40%
  - seniority fit (title match heuristics)         20%
  - sector fit (target sectors ∩ company sector)   20%
  - location fit (target locations vs job location)20%

Phase-2 swap: replace keyword overlap with embedding cosine via Chroma.
"""

from __future__ import annotations

import re

from pega_agent.db import save_matches
from pega_agent.models import JobPosting, MatchScore, Profile

SENIORITY_HINTS = {
    "intern": ["intern", "practicante", "práctica"],
    "junior": ["junior", "jr"],
    "mid": ["analyst", "analista", "specialist"],
    "senior": ["senior", "sr", "lead"],
    "lead": ["lead", "principal", "staff"],
    "manager": ["manager", "gerente", "jefe", "head of"],
    "director": ["director", "directora"],
    "vp": ["vp", "vice president", "vicepresidente"],
    "c-level": ["cto", "ceo", "cfo", "coo", "cio", "cdo", "cpo"],
}

_WORD = re.compile(r"[a-záéíóúñü0-9\-\+\.#]+", re.IGNORECASE)


def _tokens(text: str) -> set[str]:
    return {m.group(0).lower() for m in _WORD.finditer(text or "")}


def _skill_overlap(profile: Profile, job: JobPosting) -> float:
    if not profile.skills:
        return 0.0
    desc_tokens = _tokens(job.description + " " + job.title)
    hits = sum(1 for s in profile.skills if s.lower() in desc_tokens)
    return min(1.0, hits / max(5, len(profile.skills)))


def _seniority_fit(profile: Profile, job: JobPosting) -> float:
    target = profile.target_seniority
    title = (job.title or "").lower() + " " + (job.seniority or "").lower()
    target_hits = any(h in title for h in SENIORITY_HINTS.get(target, []))
    if target_hits:
        return 1.0
    # adjacent seniorities still pass with reduced score
    levels = list(SENIORITY_HINTS.keys())
    idx = levels.index(target)
    for delta in (1, -1):
        j = idx + delta
        if 0 <= j < len(levels) and any(h in title for h in SENIORITY_HINTS[levels[j]]):
            return 0.5
    return 0.0


def _sector_fit(profile: Profile, job: JobPosting) -> float:
    if not profile.target_sectors:
        return 0.5  # neutral
    blob = (job.description + " " + job.company).lower()
    hits = sum(1 for s in profile.target_sectors if s.lower() in blob)
    return min(1.0, hits / len(profile.target_sectors))


def _location_fit(profile: Profile, job: JobPosting) -> float:
    if not job.location:
        return 0.5
    loc = job.location.lower()
    if any(t.lower() in loc for t in profile.locations_open_to):
        return 1.0
    if job.remote:
        return 0.8
    return 0.1


def score_job(profile: Profile, job: JobPosting) -> MatchScore:
    skill = _skill_overlap(profile, job)
    sen = _seniority_fit(profile, job)
    sec = _sector_fit(profile, job)
    loc = _location_fit(profile, job)
    raw = 100 * (0.40 * skill + 0.20 * sen + 0.20 * sec + 0.20 * loc)
    rationale = (
        f"skills {skill:.2f} · seniority {sen:.2f} · sector {sec:.2f} · location {loc:.2f}"
    )
    return MatchScore(
        job_id=job.id,
        score=round(raw, 2),
        rationale=rationale,
        skill_overlap=skill,
        seniority_fit=sen,
        sector_fit=sec,
        location_fit=loc,
    )


def rank(profile: Profile, jobs: list[JobPosting]) -> list[MatchScore]:
    scored = [score_job(profile, j) for j in jobs]
    scored.sort(key=lambda s: s.score, reverse=True)
    save_matches(scored)
    return scored
