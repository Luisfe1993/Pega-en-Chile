"""Discovery Agent: fans out across configured adapters, dedups, persists."""

from __future__ import annotations

from rich.console import Console

from pega_agent.db import save_jobs
from pega_agent.models import JobPosting

from .adapters.base import JobSource
from .adapters.getonboard import GetOnBoardAdapter
from .adapters.jobspy_adapter import JobSpyAdapter

console = Console()


def default_sources() -> list[JobSource]:
    return [
        GetOnBoardAdapter(),
        JobSpyAdapter(sites=["linkedin", "indeed"]),
    ]


def discover(
    queries: list[str],
    sources: list[JobSource] | None = None,
    location: str = "Santiago, Chile",
    limit_per_query: int = 30,
) -> list[JobPosting]:
    sources = sources or default_sources()
    seen: dict[str, JobPosting] = {}
    for src in sources:
        for q in queries:
            try:
                console.log(f"[discovery] {src.name} ← '{q}'")
                hits = src.search(q, location=location, limit=limit_per_query)
            except Exception as e:  # adapter failure should not kill the run
                console.log(f"[discovery] {src.name} failed: {e}")
                continue
            for h in hits:
                seen.setdefault(h.id, h)
    jobs = list(seen.values())
    inserted = save_jobs(jobs)
    console.log(f"[discovery] {len(jobs)} unique jobs, {inserted} new")
    return jobs
