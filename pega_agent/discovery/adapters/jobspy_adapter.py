"""LinkedIn / Indeed / Glassdoor via the python-jobspy library.

Throttle aggressively. These boards' ToS prohibit scraping; use at your
own risk and for personal research only.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from pega_agent.models import JobPosting

from .base import JobSource


def _hash_id(source: str, url: str) -> str:
    return hashlib.sha1(f"{source}|{url}".encode()).hexdigest()[:16]


class JobSpyAdapter(JobSource):
    name = "jobspy"

    def __init__(self, sites: list[str] | None = None) -> None:
        self.sites = sites or ["linkedin", "indeed", "glassdoor"]

    def search(
        self,
        query: str,
        location: str = "Santiago, Chile",
        limit: int = 50,
    ) -> list[JobPosting]:
        try:
            from jobspy import scrape_jobs  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "python-jobspy is not installed. Run: pip install python-jobspy"
            ) from e

        df = scrape_jobs(
            site_name=self.sites,
            search_term=query,
            location=location,
            results_wanted=limit,
            country_indeed="chile",
        )
        return [self._to_posting(row) for _, row in df.iterrows()]

    def _to_posting(self, row: Any) -> JobPosting:
        url = str(row.get("job_url", "") or row.get("url", ""))
        source = str(row.get("site", "jobspy"))
        return JobPosting(
            id=_hash_id(source, url),
            source=source,
            url=url,
            title=str(row.get("title", "")),
            company=str(row.get("company", "")),
            location=str(row.get("location", "") or "") or None,
            remote=bool(row.get("is_remote")) if "is_remote" in row else None,
            posted_at=_parse_dt(row.get("date_posted")),
            description=str(row.get("description", "") or ""),
            raw={k: (str(v) if v is not None else None) for k, v in dict(row).items()},
        )


def _parse_dt(v: Any) -> datetime | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v
    try:
        return datetime.fromisoformat(str(v))
    except ValueError:
        return None
