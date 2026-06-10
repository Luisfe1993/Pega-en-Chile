"""Matcher v2: combines Profile + Search to score and filter jobs.

Pipeline:
  1. Apply hard filters from search.yaml (drop jobs that fail).
  2. Score remaining jobs across weighted soft signals.
  3. Persist scores to SQLite.

Channels:
  - semantic     : sentence-transformer cosine of profile blob vs JD
  - seniority    : title-level vs company-size expectations
  - skills       : preferred/nice-to-have skill overlap with JD
  - people_mgmt  : detection of people-management cues vs preference
  - company_size : size-aware level match
  - location     : location_open intersection
  - compensation : disclosed salary vs min/desired

The old `score_job(profile, job)` is kept for backward compatibility.
"""

from __future__ import annotations

import re

from pega_agent.db import save_matches
from pega_agent.matcher import embeddings
from pega_agent.matcher.agent import (  # reuse helpers from v1
    SENIORITY_HINTS,
    _profile_blob,
    _semantic_fit,
    _skill_overlap,
    _tokens,
)
from pega_agent.models import (
    CompanySize,
    JobPosting,
    MatchScore,
    Profile,
    Search,
)

# ---- Helpers --------------------------------------------------------------

_PEOPLE_MGMT_HINTS = [
    "manage a team", "lead a team", "lead the team", "leading the team",
    "people management", "direct reports", "team of", "manage team",
    "leads a team", "team leadership",
    # ES
    "lidera el equipo", "liderar el equipo", "lideras", "liderarás",
    "gestionar equipo", "gestionarás", "tu equipo", "equipo a cargo",
    "personas a cargo", "personas a su cargo", "gerenciar",
]

_LEVEL_RX = {
    "c-level": re.compile(r"\b(c[eo]o|cfo|cto|cio|cpo|coo|cdo|chief\s+\w+\s+officer)\b", re.I),
    "vp": re.compile(r"\b(vp|vice\s*president|vicepresidente?)\b", re.I),
    "director": re.compile(r"\b(director(a)?|head\s+of)\b", re.I),
    "manager": re.compile(r"\b(manager|gerente|jefe)\b", re.I),
    "lead": re.compile(r"\b(lead|líder|principal|staff)\b", re.I),
    "senior": re.compile(r"\b(senior|sr\.?)\b", re.I),
}


def _detect_level(text: str) -> str | None:
    """Return the most senior level token found in title/JD."""
    for level in ["c-level", "vp", "director", "manager", "lead", "senior"]:
        if _LEVEL_RX[level].search(text or ""):
            return level
    return None


def _detect_company_size(search: Search, company: str) -> CompanySize:
    """Cheap default: known-large list, else 'mid'. Research agent can refine later."""
    if not company:
        return "mid"
    c = company.lower()
    for big in search.known_large_companies:
        if big in c:
            return "large"
    return "mid"


def _detect_people_management(job: JobPosting) -> float:
    """0..1 likelihood the role manages people based on JD/title cues."""
    blob = (job.title or "") + " " + (job.description or "")
    blob_l = blob.lower()
    hits = sum(1 for h in _PEOPLE_MGMT_HINTS if h in blob_l)
    if hits >= 2:
        return 1.0
    if hits == 1:
        return 0.7
    # title-based fallback
    if _LEVEL_RX["c-level"].search(blob) or _LEVEL_RX["vp"].search(blob):
        return 0.9
    if _LEVEL_RX["director"].search(blob) or _LEVEL_RX["manager"].search(blob):
        return 0.6
    return 0.1


# ---- Hard filters ---------------------------------------------------------


def passes_hard_filters(search: Search, job: JobPosting) -> tuple[bool, str]:
    """Return (passes, reason_if_not)."""
    title = (job.title or "").lower()
    desc = (job.description or "").lower()
    company = (job.company or "").lower()

    for bad in search.excluded_titles:
        if bad.lower() in title:
            return False, f"title contains excluded term '{bad}'"

    for bad in search.excluded_industries:
        b = bad.lower().strip()
        if not b:
            continue
        if b in company:
            return False, f"company '{job.company}' matches excluded industry/firm '{bad}'"

    for bad in search.dealbreaker_keywords:
        if bad.lower() in desc:
            return False, f"description has dealbreaker '{bad}'"

    if search.min_comp_clp and job.salary_max_clp:
        # Drop only if MAX disclosed is below floor (very confident signal).
        if job.salary_max_clp < search.min_comp_clp:
            return (
                False,
                f"max comp {job.salary_max_clp:,} CLP < floor {search.min_comp_clp:,}",
            )

    return True, ""


# ---- Soft signals ---------------------------------------------------------


def _seniority_fit_v2(search: Search, job: JobPosting, size: CompanySize) -> float:
    """Does the role's level match the user's expectations for this size?"""
    accepted = []
    for t in search.company_size_targets:
        if t.size == size:
            accepted = [a.lower() for a in t.target_levels]
            break
    if not accepted:
        return 0.5  # neutral if no target defined

    detected = _detect_level(f"{job.title} {job.seniority or ''}")
    if detected and detected in accepted:
        return 1.0
    # adjacent: e.g. "director" when target is "vp"
    order = ["senior", "lead", "manager", "director", "vp", "c-level"]
    if detected and detected in order:
        d_idx = order.index(detected)
        for a in accepted:
            if a in order and abs(order.index(a) - d_idx) == 1:
                return 0.5
    return 0.0


def _skills_fit_v2(profile: Profile, search: Search, job: JobPosting) -> float:
    """Weighted: preferred_skills (1.0 each) + nice_to_have (0.5 each), capped 1.0."""
    blob = _tokens(job.description + " " + job.title)
    preferred = [s for s in search.preferred_skills if s.lower() in blob]
    nice = [s for s in search.nice_to_have_skills if s.lower() in blob]
    score = 0.0
    if search.preferred_skills:
        score += 0.7 * (len(preferred) / max(3, len(search.preferred_skills)))
    if search.nice_to_have_skills:
        score += 0.3 * (len(nice) / max(3, len(search.nice_to_have_skills)))
    # also fall back to profile skills
    if not score and profile.skills:
        score = _skill_overlap(profile, job)
    return min(1.0, score)


def _people_mgmt_fit(search: Search, job: JobPosting) -> float:
    """Match detected people-mgmt likelihood against the user preference."""
    detected = _detect_people_management(job)
    pref = search.people_management
    if pref == "required":
        return detected  # higher = better; if 0.1 → bad
    if pref == "preferred":
        return 0.5 + 0.5 * detected  # baseline 0.5, boost up to 1.0
    if pref == "avoid":
        return 1.0 - detected
    return 0.5  # neutral


def _company_size_fit(search: Search, size: CompanySize) -> float:
    """Did the user define a target for this size at all?"""
    sizes_set = {t.size for t in search.company_size_targets}
    return 1.0 if size in sizes_set else 0.3


def _location_fit_v2(search: Search, job: JobPosting) -> float:
    if not job.location:
        return 0.5
    loc = job.location.lower()
    if any(t.lower() in loc for t in search.locations):
        return 1.0
    if job.remote and "remote" in [w.lower() for w in search.locations]:
        return 0.9
    if job.remote:
        return 0.7
    return 0.0


def _comp_fit(search: Search, job: JobPosting) -> float | None:
    """None when undisclosed. 1.0 if at or above floor, scaled below."""
    if not search.min_comp_clp:
        return None
    if not (job.salary_min_clp or job.salary_max_clp):
        return None
    salary = job.salary_max_clp or job.salary_min_clp
    if salary >= search.min_comp_clp:
        return 1.0
    return max(0.0, salary / search.min_comp_clp)


# Signals that the role has international / multi-country scope.
# Weighted: STRONG signals count 1.5x, plain hits count 1.0x; capped at 1.0.
_INTL_STRONG = (
    "latam", "latin america", "latin-american",
    "americas", "the americas",
    "multi-country", "multi country", "multicountry",
    "multinational",
    "global product", "global team", "global role",
    "regional director", "regional vp", "regional vice president",
    "country manager",
    "cross-border", "cross border",
    "across countries", "across markets", "across regions",
    "multiple countries", "multiple markets",
    "south america", "central america",
    "andean", "cono sur",
    "global organization", "global organisation",
    "international team", "international markets",
    "international stakeholders", "international scope",
)
_INTL_WEAK = (
    "international",
    "global",
    "regional",
    "worldwide",
    "headquarter", "headquarters",
    "international experience",
    "english required", "english fluency",
    "english and spanish", "bilingual",
)


def _international_exposure(job: JobPosting) -> float:
    """0..1 score for how 'international' the role's scope appears."""
    blob = ((job.title or "") + " " + (job.description or "")).lower()
    if not blob.strip():
        return 0.0
    strong = sum(1 for k in _INTL_STRONG if k in blob)
    weak = sum(1 for k in _INTL_WEAK if k in blob)
    # 1 strong hit ~= 0.5; 2 strong ~= 0.9; 1 weak ~= 0.15
    raw = 0.5 * strong + 0.15 * weak
    return min(1.0, raw)


# ---- Public API -----------------------------------------------------------


def score_job_v2(
    profile: Profile, search: Search, job: JobPosting
) -> tuple[MatchScore | None, str]:
    """Return (score, dropped_reason). If dropped, score is None."""
    ok, reason = passes_hard_filters(search, job)
    if not ok:
        return None, reason

    size = _detect_company_size(search, job.company)
    sem = _semantic_fit(profile, job)
    sen = _seniority_fit_v2(search, job, size)
    sk = _skills_fit_v2(profile, search, job)
    pm = _people_mgmt_fit(search, job)
    cs = _company_size_fit(search, size)
    loc = _location_fit_v2(search, job)
    comp = _comp_fit(search, job)
    intl = _international_exposure(job)

    w = search.weights
    # Drop the compensation channel if undisclosed and renormalize.
    parts: dict[str, tuple[float, float]] = {
        "semantic": (w.semantic, sem),
        "seniority": (w.seniority, sen),
        "skills": (w.skills, sk),
        "people_mgmt": (w.people_mgmt, pm),
        "company_size": (w.company_size, cs),
        "location": (w.location, loc),
        "international_exposure": (w.international_exposure, intl),
    }
    if comp is not None:
        parts["compensation"] = (w.compensation, comp)

    total_w = sum(weight for weight, _ in parts.values()) or 1.0
    raw = 100 * sum((weight / total_w) * value for weight, value in parts.values())

    bits = [
        f"sen {sen:.2f}",
        f"size {size}({cs:.2f})",
        f"pmgmt {pm:.2f}",
        f"sem {sem:.2f}",
        f"sk {sk:.2f}",
        f"loc {loc:.2f}",
        f"intl {intl:.2f}",
    ]
    if comp is not None:
        bits.append(f"comp {comp:.2f}")
    rationale = " · ".join(bits)

    return (
        MatchScore(
            job_id=job.id,
            score=round(raw, 2),
            rationale=rationale,
            skill_overlap=sk,
            seniority_fit=sen,
            sector_fit=cs,  # repurposed: company-size fit
            location_fit=loc,
            semantic_fit=sem,
            comp_fit=comp,
        ),
        "",
    )


def rank_v2(
    profile: Profile, search: Search, jobs: list[JobPosting]
) -> tuple[list[MatchScore], dict[str, str]]:
    """Score + filter. Returns (kept_scores, {job_id: drop_reason}) for dropped."""
    kept: list[MatchScore] = []
    dropped: dict[str, str] = {}
    # Dedup by (company_lower, title_lower) — same role posted on Indeed + LinkedIn
    # surfaces as two JobRow rows. Keep the higher-scoring one.
    best_per_key: dict[tuple[str, str], MatchScore] = {}
    for j in jobs:
        score, reason = score_job_v2(profile, search, j)
        if score is None:
            dropped[j.id] = reason
            continue
        key = ((j.company or "").strip().lower(), (j.title or "").strip().lower())
        prev = best_per_key.get(key)
        if prev is None or score.score > prev.score:
            if prev is not None:
                dropped[prev.job_id] = f"duplicate of higher-scoring posting for '{j.company} · {j.title}'"
            best_per_key[key] = score
        else:
            dropped[j.id] = f"duplicate of higher-scoring posting for '{j.company} · {j.title}'"
    kept = list(best_per_key.values())
    kept.sort(key=lambda s: s.score, reverse=True)
    save_matches(kept)
    return kept, dropped
