"""Markdown digest writer. Produces a human-readable summary of a Pega run.

Writes to `data/digests/<date>__<thread>.md`. The digest is the primary
deliverable for the new workflow: the user opens it instead of Streamlit.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime
from pathlib import Path

import yaml

from pega_agent.config import ROOT
from pega_agent.db import (
    load_brief,
    load_cover_letter,
    load_job,
    load_matches,
    load_tailored_cv,
)
from pega_agent.models import JobPosting, MatchScore, Profile, Search

DEFAULT_RECRUITERS_PATH = ROOT / "data" / "recruiters.yaml"


def _watchlist_companies(recruiters_path: Path) -> list[str]:
    """Pull the canonical watchlist (target firms + warm contacts firms) from yaml.

    Returns lowercased substrings; empty list if file missing.
    """
    if not recruiters_path.exists():
        return []
    data = yaml.safe_load(recruiters_path.read_text(encoding="utf-8")) or {}
    names: set[str] = set()
    for f in data.get("target_firms", []) or []:
        n = (f.get("name") or "").strip().lower()
        if n:
            names.add(n)
    for w in data.get("warm_contacts", []) or []:
        n = (w.get("firm") or "").strip().lower()
        if n:
            names.add(n)
    # Also pick up explicit `watchlist:` section if present
    for n in data.get("watchlist", []) or []:
        if isinstance(n, str) and n.strip():
            names.add(n.strip().lower())
    return sorted(names)


def _company_matches_watchlist(company: str, watchlist: list[str]) -> bool:
    if not watchlist:
        return False
    c = company.lower()
    return any(w in c or c in w for w in watchlist)


def _load_prior_top_ids(prior_path: Path | None) -> set[str]:
    """Extract job-link tokens from a prior digest to compute deltas.

    We just look for source links in the markdown — cheap but reliable.
    """
    if not prior_path or not prior_path.exists():
        return set()
    txt = prior_path.read_text(encoding="utf-8")
    return set(re.findall(r"\[link\]\(([^)]+)\)", txt))


def _job_block(
    rank: int, score: MatchScore, job: JobPosting, has_cv: bool, has_cover: bool, has_brief: bool
) -> str:
    parts: list[str] = []
    parts.append(f"### {rank}. {job.title} — {job.company} · {score.score:.1f}/100")
    parts.append("")
    location = job.location or "—"
    remote = " · remote" if job.remote else ""
    parts.append(f"- **Location**: {location}{remote}")
    if job.posted_at:
        # Render as YYYY-MM-DD + age in days for at-a-glance freshness.
        age_days = (datetime.now() - job.posted_at).days
        age = "today" if age_days == 0 else f"{age_days}d ago"
        parts.append(f"- **Posted**: {job.posted_at.strftime('%Y-%m-%d')} ({age})")
    if job.salary_min_clp or job.salary_max_clp:
        lo = f"{job.salary_min_clp:,}" if job.salary_min_clp else "?"
        hi = f"{job.salary_max_clp:,}" if job.salary_max_clp else "?"
        parts.append(f"- **Comp (CLP)**: {lo} – {hi}")
    if job.seniority:
        parts.append(f"- **Seniority tag**: {job.seniority}")
    parts.append(f"- **Source**: {job.source} · [link]({job.url})")
    parts.append(f"- **Score breakdown**: {score.rationale}")
    artifacts: list[str] = []
    if has_cv:
        artifacts.append("tailored CV")
    if has_cover:
        artifacts.append("cover letter")
    if has_brief:
        artifacts.append("company brief")
    if artifacts:
        parts.append(f"- **Generated artifacts**: {', '.join(artifacts)}")
    if job.description:
        snippet = " ".join(job.description.split())[:400]
        parts.append("")
        parts.append(f"> {snippet}…")
    parts.append("")
    return "\n".join(parts)


def _drop_summary(dropped: dict[str, str]) -> str:
    if not dropped:
        return ""
    counts = Counter(dropped.values()).most_common(8)
    lines = ["## Filtered out", ""]
    lines.append(f"{len(dropped)} jobs dropped by hard filters. Top reasons:")
    lines.append("")
    for reason, n in counts:
        lines.append(f"- **{n}×** {reason}")
    lines.append("")
    return "\n".join(lines)


def render_digest(
    profile: Profile,
    search: Search,
    scores: list[MatchScore],
    dropped: dict[str, str],
    total_discovered: int,
    top_n: int = 15,
    *,
    watchlist_only: bool = False,
    watchlist: list[str] | None = None,
    prior_digest_path: Path | None = None,
) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines: list[str] = []

    # Resolve watchlist + apply filter early so summary numbers stay honest.
    wl = watchlist if watchlist is not None else _watchlist_companies(DEFAULT_RECRUITERS_PATH)
    filtered_scores = scores
    if watchlist_only:
        kept: list[MatchScore] = []
        for s in scores:
            job = load_job(s.job_id)
            if job and _company_matches_watchlist(job.company, wl):
                kept.append(s)
        filtered_scores = kept

    prior_links = _load_prior_top_ids(prior_digest_path)

    title_suffix = " — Watchlist" if watchlist_only else ""
    lines.append(f"# Pega Digest{title_suffix} — {now}")
    lines.append("")
    lines.append(f"**{profile.name}** · {profile.headline or ''}")
    lines.append("")
    lines.append("## Run summary")
    lines.append("")
    lines.append(f"- Discovered: **{total_discovered}** postings")
    lines.append(f"- Passed hard filters: **{len(scores)}**")
    if watchlist_only:
        lines.append(
            f"- On watchlist ({len(wl)} firms tracked): **{len(filtered_scores)}**"
        )
    lines.append(f"- Dropped: **{len(dropped)}**")
    lines.append(f"- Showing top **{min(top_n, len(filtered_scores))}** below")
    lines.append("")
    lines.append("## Search criteria recap")
    lines.append("")
    lines.append(
        f"- **Min comp**: {search.min_comp_clp:,} CLP/mo"
        if search.min_comp_clp
        else "- **Min comp**: not set"
    )
    lines.append(f"- **People management**: {search.people_management}")
    size_lines = [
        f"  - {t.size}: {', '.join(t.target_levels)}" for t in search.company_size_targets
    ]
    if size_lines:
        lines.append("- **Target levels by company size**:")
        lines.extend(size_lines)
    lines.append(f"- **Locations**: {', '.join(search.locations)}")
    if watchlist_only and wl:
        lines.append(f"- **Watchlist firms** ({len(wl)}): {', '.join(wl[:25])}")
    lines.append("")

    # Deltas vs. prior digest
    if prior_links:
        cur_links = {load_job(s.job_id).url for s in filtered_scores if load_job(s.job_id)}
        new_links = cur_links - prior_links
        gone_links = prior_links - cur_links
        if new_links or gone_links:
            lines.append("## Changes since last digest")
            lines.append("")
            if new_links:
                lines.append(f"- **New this run**: {len(new_links)} posting(s)")
            if gone_links:
                lines.append(f"- **No longer present**: {len(gone_links)} posting(s)")
            lines.append("")

    lines.append("## Top matches")
    lines.append("")

    for rank, s in enumerate(filtered_scores[:top_n], start=1):
        job = load_job(s.job_id)
        if not job:
            continue
        has_cv = load_tailored_cv(s.job_id) is not None
        has_cover = load_cover_letter(s.job_id) is not None
        has_brief = load_brief(job.company) is not None
        block = _job_block(rank, s, job, has_cv, has_cover, has_brief)
        if prior_links and job.url not in prior_links:
            block = block.replace(
                f"### {rank}. ", f"### {rank}. [NEW] ", 1
            )
        lines.append(block)

    if not watchlist_only and dropped:
        lines.append(_drop_summary(dropped))

    return "\n".join(lines)


def write_digest(
    profile: Profile,
    search: Search,
    scores: list[MatchScore],
    dropped: dict[str, str],
    total_discovered: int,
    out_dir: Path,
    thread: str = "current",
    top_n: int = 15,
    *,
    watchlist_only: bool = False,
    prior_digest_path: Path | None = None,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    suffix = "__watchlist" if watchlist_only else ""
    path = out_dir / f"{stamp}__{thread}{suffix}.md"
    # If no explicit prior provided, auto-pick the latest matching digest.
    if prior_digest_path is None and out_dir.exists():
        pattern = f"*__{thread}{suffix}.md"
        candidates = sorted(out_dir.glob(pattern))
        if candidates:
            prior_digest_path = candidates[-1]
    path.write_text(
        render_digest(
            profile,
            search,
            scores,
            dropped,
            total_discovered,
            top_n=top_n,
            watchlist_only=watchlist_only,
            prior_digest_path=prior_digest_path,
        ),
        encoding="utf-8",
    )
    return path


def write_digest_from_db(
    profile: Profile,
    search: Search,
    out_dir: Path,
    thread: str = "current",
    top_n: int = 15,
    *,
    watchlist_only: bool = False,
    prior_digest_path: Path | None = None,
) -> Path:
    """Regenerate a digest from whatever's in the DB right now (no new discovery)."""
    # Pull a much bigger pool when filtering, since most will be off-watchlist.
    pull = top_n * (20 if watchlist_only else 4)
    scores = load_matches(limit=pull)
    return write_digest(
        profile=profile,
        search=search,
        scores=scores,
        dropped={},
        total_discovered=len(scores),
        out_dir=out_dir,
        thread=thread,
        top_n=top_n,
        watchlist_only=watchlist_only,
        prior_digest_path=prior_digest_path,
    )
