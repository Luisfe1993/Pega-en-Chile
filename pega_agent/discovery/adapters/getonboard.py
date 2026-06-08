"""GetOnBoard.com adapter — Chilean / Latam tech jobs.

GetOnBoard exposes a public read API for job listings. No auth needed for
basic search; pass a token via env to lift rate limits.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

import httpx

from pega_agent.config import settings
from pega_agent.models import JobPosting

from .base import JobSource

API_ROOT = "https://www.getonbrd.com/api/v0"


def _hash_id(source: str, url: str) -> str:
    return hashlib.sha1(f"{source}|{url}".encode()).hexdigest()[:16]


class GetOnBoardAdapter(JobSource):
    name = "getonboard"

    def search(
        self,
        query: str,
        location: str = "Santiago, Chile",
        limit: int = 50,
    ) -> list[JobPosting]:
        headers = {}
        if settings.getonboard_token:
            headers["Authorization"] = f"Token {settings.getonboard_token}"
        params = {"query": query, "per_page": min(limit, 50), "expand": "[\"company\"]"}
        url = f"{API_ROOT}/search/jobs"
        with httpx.Client(timeout=20.0, headers=headers) as client:
            r = client.get(url, params=params)
            r.raise_for_status()
            payload = r.json()
        items = payload.get("data", [])
        return [self._to_posting(item) for item in items[:limit]]

    def _to_posting(self, item: dict[str, Any]) -> JobPosting:
        attrs = item.get("attributes", {})
        company_name = (
            (attrs.get("company") or {}).get("data", {}).get("attributes", {}).get("name")
            or attrs.get("company_name")
            or ""
        )
        url = attrs.get("public_url", "")
        posted_ts = attrs.get("published_at")
        posted = (
            datetime.fromtimestamp(posted_ts)
            if isinstance(posted_ts, (int, float))
            else None
        )
        return JobPosting(
            id=_hash_id(self.name, url),
            source=self.name,
            url=url,
            title=attrs.get("title", ""),
            company=str(company_name),
            location=attrs.get("country") or "Chile",
            remote=attrs.get("remote") in (True, "fully", "partially"),
            seniority=attrs.get("seniority"),
            posted_at=posted,
            description=attrs.get("description", "") or attrs.get("functions", "") or "",
            salary_min_clp=None,
            salary_max_clp=None,
            raw=attrs,
        )
