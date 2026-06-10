"""Matcher Agent: scores each job 0..100 against the candidate profile.

Scoring blends (when embeddings are available):
  - semantic fit (cosine of profile-blob vs JD)    35%
  - keyword overlap (skills ∩ description)         15%
  - seniority fit (title heuristics)               20%
  - sector fit (target sectors ∩ company sector)   15%
  - location fit (target locations vs job location)15%

If sentence-transformers / the embedding model can't load, the semantic
channel returns 0 and the other channels are renormalized to 100%.
"""

from __future__ import annotations

import re

from pega_agent.db import save_matches
from pega_agent.matcher import embeddings
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
    sem = _semantic_fit(profile, job)

    if embeddings.is_available():
        weights = {"sem": 0.35, "skill": 0.15, "sen": 0.20, "sec": 0.15, "loc": 0.15}
    else:
        weights = {"sem": 0.00, "skill": 0.40, "sen": 0.20, "sec": 0.20, "loc": 0.20}

    raw = 100 * (
        weights["sem"] * sem
        + weights["skill"] * skill
        + weights["sen"] * sen
        + weights["sec"] * sec
        + weights["loc"] * loc
    )
    rationale = (
        f"sem {sem:.2f} · skills {skill:.2f} · seniority {sen:.2f} · "
        f"sector {sec:.2f} · location {loc:.2f}"
    )
    return MatchScore(
        job_id=job.id,
        score=round(raw, 2),
        rationale=rationale,
        skill_overlap=skill,
        seniority_fit=sen,
        sector_fit=sec,
        location_fit=loc,
        semantic_fit=sem,
    )


def _profile_blob(profile: Profile) -> str:
    parts = [
        profile.headline or "",
        profile.summary or "",
        " ".join(profile.skills),
        " ".join(profile.target_roles),
        " ".join(profile.target_sectors),
    ]
    for exp in profile.experience[:6]:
        parts.append(f"{exp.title} @ {exp.company}: {' · '.join(exp.bullets[:3])}")
    return "\n".join(p for p in parts if p)


def _semantic_fit(profile: Profile, job: JobPosting) -> float:
    if not embeddings.is_available():
        return 0.0
    profile_text = _profile_blob(profile)
    job_text = f"{job.title}\n{job.description[:2000]}"
    vecs = embeddings.embed_texts([profile_text, job_text])
    if vecs.shape[0] < 2:
        return 0.0
    # e5 cosines sit in ~[0.75, 1.0] even for unrelated text; rescale that band to [0, 1]
    cos = float(embeddings.cosine(vecs[0], vecs[1]))
    return max(0.0, min(1.0, (cos - 0.75) / 0.25))


def rank(profile: Profile, jobs: list[JobPosting]) -> list[MatchScore]:
    scored = [score_job(profile, j) for j in jobs]
    scored.sort(key=lambda s: s.score, reverse=True)
    save_matches(scored)
    return scored
