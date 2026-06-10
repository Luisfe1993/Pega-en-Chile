"""LangGraph state machine.

  profile → discovery → match → research → tailor → outreach → quality_gate

The Quality Gate calls `interrupt()` to pause the run; the human (via the
Streamlit approval queue or `pega resume`) provides per-artifact decisions,
which are persisted as `ApprovalDecision` rows. Nothing leaves the machine
without an explicit `approved` (or `edited`) status.

A SQLite checkpointer (`langgraph-checkpoint-sqlite`) persists graph state
between the pause and resume, keyed by `thread_id`.
"""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, StateGraph
from langgraph.types import interrupt
from rich.console import Console

from pega_agent.config import settings
from pega_agent.db import save_approval
from pega_agent.digest import write_digest
from pega_agent.discovery.agent import discover
from pega_agent.matcher.agent_v2 import rank_v2
from pega_agent.models import (
    ApprovalDecision,
    CompanyBrief,
    CoverLetter,
    JobPosting,
    MatchScore,
    OutreachDraft,
    Profile,
    Search,
    TailoredCV,
)
from pega_agent.network.loader import load_network
from pega_agent.outreach.agent import draft_outreach
from pega_agent.research.agent import research_company
from pega_agent.tailor.agent import draft_cover_letter, tailor_cv

console = Console()


class PegaState(TypedDict, total=False):
    profile: Profile
    search: Search
    queries: list[str]
    location: str
    jobs: list[JobPosting]
    scores: list[MatchScore]
    dropped: dict[str, str]
    digest_path: str
    briefs: list[CompanyBrief]
    research_top_n: int
    tailor_top_n: int
    tailored: list[TailoredCV]
    cover_letters: list[CoverLetter]
    outreach: list[OutreachDraft]
    approved_ids: list[str]


# ---------- nodes --------------------------------------------------------


def node_discover(state: PegaState) -> PegaState:
    search = state.get("search")
    queries = state.get("queries") or (search.queries if search else None) or ["product manager"]
    jobs = discover(
        queries=queries,
        location=state.get("location", "Santiago, Chile"),
    )
    return {"jobs": jobs}


def node_match(state: PegaState) -> PegaState:
    search = state.get("search") or Search()
    scores, dropped = rank_v2(state["profile"], search, state["jobs"])
    console.log(
        f"[match] {len(scores)} kept · {len(dropped)} dropped "
        f"(of {len(state['jobs'])} discovered)"
    )
    return {"scores": scores, "dropped": dropped}


def node_research(state: PegaState) -> PegaState:
    top_n = state.get("research_top_n", 5)
    job_by_id = {j.id: j for j in state.get("jobs", [])}
    top_scores = state.get("scores", [])[:top_n]

    briefs: list[CompanyBrief] = []
    seen: set[str] = set()
    for s in top_scores:
        job = job_by_id.get(s.job_id)
        if not job or not job.company or job.company.lower() in seen:
            continue
        seen.add(job.company.lower())
        try:
            console.log(f"[research] {job.company}")
            briefs.append(research_company(job.company, posting=job))
        except Exception as e:
            console.log(f"[research] {job.company} failed: {e}")
    return {"briefs": briefs}


def node_tailor(state: PegaState) -> PegaState:
    top_n = state.get("tailor_top_n", 3)
    job_by_id = {j.id: j for j in state.get("jobs", [])}
    brief_by_company = {b.company.lower(): b for b in state.get("briefs", [])}
    top_scores = state.get("scores", [])[:top_n]

    tailored: list[TailoredCV] = []
    covers: list[CoverLetter] = []
    for s in top_scores:
        job = job_by_id.get(s.job_id)
        if not job:
            continue
        brief = brief_by_company.get(job.company.lower())
        try:
            console.log(f"[tailor] {job.title} @ {job.company}")
            cv = tailor_cv(state["profile"], job, brief=brief)
            tailored.append(cv)
            covers.append(draft_cover_letter(state["profile"], job, cv, brief=brief))
        except Exception as e:
            console.log(f"[tailor] {job.title} failed: {e}")
    return {"tailored": tailored, "cover_letters": covers}


def node_outreach(state: PegaState) -> PegaState:
    contacts = load_network()
    job_by_id = {j.id: j for j in state.get("jobs", [])}
    brief_by_company = {b.company.lower(): b for b in state.get("briefs", [])}
    cv_by_job = {c.job_id: c for c in state.get("tailored", [])}

    drafts: list[OutreachDraft] = []
    for cv in state.get("tailored", []):
        job = job_by_id.get(cv.job_id)
        if not job:
            continue
        brief = brief_by_company.get(job.company.lower())
        try:
            console.log(f"[outreach] {job.company}")
            drafts.append(
                draft_outreach(
                    state["profile"],
                    job,
                    contacts,
                    brief=brief,
                    cv=cv_by_job.get(job.id),
                )
            )
        except Exception as e:
            console.log(f"[outreach] {job.company} failed: {e}")
    return {"outreach": drafts}


def node_quality_gate(state: PegaState) -> PegaState:
    """HITL interrupt. The Streamlit UI (or `pega resume`) supplies decisions."""
    if not settings.pega_human_in_the_loop:
        raise RuntimeError(
            "PEGA_HUMAN_IN_THE_LOOP=false is not supported. The Quality Gate is mandatory."
        )

    payload = {
        "tailored": [c.model_dump() for c in state.get("tailored", [])],
        "cover_letters": [c.model_dump() for c in state.get("cover_letters", [])],
        "outreach": [o.model_dump() for o in state.get("outreach", [])],
    }
    # `interrupt` pauses the graph until the run is resumed with a value.
    decisions_raw = interrupt(payload)

    decisions = [ApprovalDecision(**d) for d in (decisions_raw or [])]
    approved_ids: set[str] = set()
    for d in decisions:
        save_approval(d)
        if d.status in {"approved", "edited"}:
            approved_ids.add(d.job_id)
    return {"approved_ids": sorted(approved_ids)}


def node_digest(state: PegaState) -> PegaState:
    """Write the Markdown digest at the end of the run."""
    search = state.get("search") or Search()
    out_dir = settings.pega_db_path.parent / "digests"
    path = write_digest(
        profile=state["profile"],
        search=search,
        scores=state.get("scores", []),
        dropped=state.get("dropped", {}),
        total_discovered=len(state.get("jobs", [])),
        out_dir=out_dir,
        thread="run",
        top_n=15,
    )
    console.log(f"[digest] wrote {path}")
    return {"digest_path": str(path)}


# ---------- graph builder ------------------------------------------------


def _checkpointer():
    """SQLite-backed checkpointer. Falls back to in-memory if unavailable."""
    try:
        import sqlite3

        from langgraph.checkpoint.sqlite import SqliteSaver

        settings.pega_db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(settings.pega_db_path), check_same_thread=False)
        return SqliteSaver(conn)
    except ImportError:
        from langgraph.checkpoint.memory import MemorySaver

        console.log(
            "[graph] langgraph-checkpoint-sqlite not installed; using in-memory checkpointer"
        )
        return MemorySaver()


def build_graph(checkpointer=None):
    g = StateGraph(PegaState)
    g.add_node("discover", node_discover)
    g.add_node("match", node_match)
    g.add_node("digest", node_digest)
    g.add_node("research", node_research)
    g.add_node("tailor", node_tailor)
    g.add_node("outreach", node_outreach)
    g.add_node("quality_gate", node_quality_gate)
    g.set_entry_point("discover")
    g.add_edge("discover", "match")
    g.add_edge("match", "digest")
    g.add_edge("digest", "research")
    g.add_edge("research", "tailor")
    g.add_edge("tailor", "outreach")
    g.add_edge("outreach", "quality_gate")
    g.add_edge("quality_gate", END)
    return g.compile(checkpointer=checkpointer or _checkpointer())
