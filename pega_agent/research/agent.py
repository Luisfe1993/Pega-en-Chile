"""Company Research Agent.

Given a company name (and optional posting context), produces a `CompanyBrief`:
  - what they do, sector, size, HQ
  - recent news headlines (last ~30d via DuckDuckGo + optional NewsAPI)
  - why this role likely exists, red flags, talking points for interviews

Cached in SQLite (`company_briefs` table) keyed by company.lower().
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import httpx
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from rich.console import Console

from pega_agent.config import settings
from pega_agent.db import load_brief, save_brief
from pega_agent.llm import get_chat_model, has_llm
from pega_agent.models import CompanyBrief, JobPosting

console = Console()


# ---------- evidence collection ------------------------------------------


def _search_duckduckgo(query: str, max_results: int = 8) -> list[dict[str, str]]:
    try:
        from duckduckgo_search import DDGS  # type: ignore
    except ImportError:
        return []
    try:
        with DDGS() as ddgs:
            return [
                {
                    "title": r.get("title", ""),
                    "snippet": r.get("body", ""),
                    "url": r.get("href", ""),
                }
                for r in ddgs.text(query, region="cl-es", max_results=max_results)
            ]
    except Exception as e:
        console.log(f"[research] ddg failed: {e}")
        return []


def _search_newsapi(company: str, days: int = 30, limit: int = 8) -> list[dict[str, str]]:
    if not settings.newsapi_key:
        return []
    since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
    params = {
        "q": company,
        "from": since,
        "language": "es",
        "sortBy": "publishedAt",
        "pageSize": limit,
        "apiKey": settings.newsapi_key,
    }
    try:
        with httpx.Client(timeout=15.0) as c:
            r = c.get("https://newsapi.org/v2/everything", params=params)
            r.raise_for_status()
            items = r.json().get("articles", [])
        return [
            {
                "title": a.get("title", ""),
                "snippet": a.get("description", "") or "",
                "url": a.get("url", ""),
            }
            for a in items
        ]
    except Exception as e:
        console.log(f"[research] newsapi failed: {e}")
        return []


def gather_evidence(company: str) -> list[dict[str, str]]:
    seen: dict[str, dict[str, str]] = {}
    for batch in (
        _search_duckduckgo(f"{company} Chile empresa qué hace"),
        _search_duckduckgo(f"{company} noticias"),
        _search_newsapi(company),
    ):
        for item in batch:
            url = item.get("url") or item.get("title", "")
            seen.setdefault(url, item)
    return list(seen.values())[:15]


# ---------- LLM synthesis ------------------------------------------------


class _BriefDraft(BaseModel):
    what_they_do: str = Field(description="1-2 sentences, neutral, factual")
    sector: str | None = None
    size: str | None = Field(default=None, description="startup | scale-up | enterprise | public co.")
    headquarters: str | None = None
    recent_news: list[str] = Field(
        default_factory=list, description="3-5 short bullets, most recent first"
    )
    why_role_exists: str | None = Field(
        default=None, description="Inferred reason this role is open right now"
    )
    red_flags: list[str] = Field(
        default_factory=list,
        description="Layoffs, lawsuits, exec churn, glassdoor patterns. Only if evidence supports it.",
    )
    talking_points: list[str] = Field(
        default_factory=list, description="3-5 angles to raise in an interview"
    )


_BRIEF_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            (
                "You are a market analyst producing a tight pre-interview brief on a "
                "Chilean (or Latam) company for a senior PM/Director candidate.\n"
                "Rules:\n"
                "  - Ground every claim in the evidence snippets. Do not invent.\n"
                "  - If evidence is thin for a field, leave it null / empty.\n"
                "  - Write in the same language as the evidence (mostly Spanish).\n"
                "  - Red flags require explicit evidence; never speculate.\n"
                "  - Talking points should connect the company's situation to what a\n"
                "    senior PM would credibly own."
            ),
        ),
        (
            "user",
            (
                "Company: {company}\n"
                "Role posting (optional): {role}\n\n"
                "Evidence snippets (JSON):\n{evidence}"
            ),
        ),
    ]
)


def research_company(
    company: str,
    posting: JobPosting | None = None,
    *,
    use_cache: bool = True,
    max_age_days: int = 7,
) -> CompanyBrief:
    if use_cache:
        cached = load_brief(company)
        if cached and (datetime.utcnow() - cached.generated_at) < timedelta(days=max_age_days):
            return cached

    evidence = gather_evidence(company)
    sources = [e["url"] for e in evidence if e.get("url")]

    if not has_llm():
        # Degraded fallback: return the raw evidence as the brief
        return CompanyBrief(
            company=company,
            what_they_do="(LLM not configured — raw evidence only)",
            recent_news=[e["title"] for e in evidence[:5]],
            sources=sources,
        )

    model = get_chat_model(temperature=0.0)
    chain = _BRIEF_PROMPT | model.with_structured_output(_BriefDraft)
    role_text = posting.title if posting else "(unspecified)"
    draft: _BriefDraft = chain.invoke(
        {
            "company": company,
            "role": role_text,
            "evidence": _trim_evidence(evidence),
        }
    )
    brief = CompanyBrief(
        company=company,
        what_they_do=draft.what_they_do,
        sector=draft.sector,
        size=draft.size,
        headquarters=draft.headquarters,
        recent_news=draft.recent_news,
        why_role_exists=draft.why_role_exists,
        red_flags=draft.red_flags,
        talking_points=draft.talking_points,
        sources=sources,
    )
    save_brief(brief)
    return brief


def _trim_evidence(items: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Cap each snippet to keep the prompt small."""
    return [
        {
            "title": it.get("title", "")[:200],
            "snippet": (it.get("snippet", "") or "")[:400],
            "url": it.get("url", ""),
        }
        for it in items
    ]
