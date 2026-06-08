"""LangGraph state machine: profile → discovery → match → research → quality-gate.

The Quality Gate node is intentionally a stub today; it will become an
`interrupt` point once we add the Outreach / Tailor agents. The graph
topology already reflects the human-in-the-loop guarantee.
"""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, StateGraph
from rich.console import Console

from pega_agent.discovery.agent import discover
from pega_agent.matcher.agent import rank
from pega_agent.models import CompanyBrief, JobPosting, MatchScore, Profile
from pega_agent.research.agent import research_company

console = Console()


class PegaState(TypedDict, total=False):
    profile: Profile
    queries: list[str]
    location: str
    jobs: list[JobPosting]
    scores: list[MatchScore]
    briefs: list[CompanyBrief]
    research_top_n: int
    approved_ids: list[str]


def node_discover(state: PegaState) -> PegaState:
    jobs = discover(
        queries=state.get("queries") or state["profile"].target_roles or ["product manager"],
        location=state.get("location", "Santiago, Chile"),
    )
    return {"jobs": jobs}


def node_match(state: PegaState) -> PegaState:
    scores = rank(state["profile"], state["jobs"])
    return {"scores": scores}


def node_research(state: PegaState) -> PegaState:
    top_n = state.get("research_top_n", 5)
    job_by_id = {j.id: j for j in state.get("jobs", [])}
    top_scores = state.get("scores", [])[:top_n]

    briefs: list[CompanyBrief] = []
    seen_companies: set[str] = set()
    for s in top_scores:
        job = job_by_id.get(s.job_id)
        if not job or not job.company:
            continue
        key = job.company.lower()
        if key in seen_companies:
            continue
        seen_companies.add(key)
        try:
            console.log(f"[research] {job.company}")
            briefs.append(research_company(job.company, posting=job))
        except Exception as e:
            console.log(f"[research] {job.company} failed: {e}")
    return {"briefs": briefs}


def node_quality_gate(state: PegaState) -> PegaState:
    # Placeholder: in Phase 4 this becomes an `interrupt` that pauses the
    # graph until the Streamlit UI approves specific job_ids for outreach.
    top = [s.job_id for s in state.get("scores", [])[:10]]
    return {"approved_ids": top}


def build_graph():
    g = StateGraph(PegaState)
    g.add_node("discover", node_discover)
    g.add_node("match", node_match)
    g.add_node("research", node_research)
    g.add_node("quality_gate", node_quality_gate)
    g.set_entry_point("discover")
    g.add_edge("discover", "match")
    g.add_edge("match", "research")
    g.add_edge("research", "quality_gate")
    g.add_edge("quality_gate", END)
    return g.compile()
