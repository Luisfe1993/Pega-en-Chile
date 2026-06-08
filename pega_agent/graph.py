"""LangGraph state machine: profile → discovery → match → (HITL gate).

The Quality Gate node is intentionally a no-op stub today; it will become an
`interrupt` point once we add the Outreach / Tailor agents. The point is that
the graph topology already reflects the human-in-the-loop guarantee.
"""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, StateGraph

from pega_agent.discovery.agent import discover
from pega_agent.matcher.agent import rank
from pega_agent.models import JobPosting, MatchScore, Profile


class PegaState(TypedDict, total=False):
    profile: Profile
    queries: list[str]
    location: str
    jobs: list[JobPosting]
    scores: list[MatchScore]
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


def node_quality_gate(state: PegaState) -> PegaState:
    # Placeholder: in Phase 4 this becomes an `interrupt` that pauses the
    # graph until the Streamlit UI approves specific job_ids for outreach.
    top = [s.job_id for s in state.get("scores", [])[:10]]
    return {"approved_ids": top}


def build_graph():
    g = StateGraph(PegaState)
    g.add_node("discover", node_discover)
    g.add_node("match", node_match)
    g.add_node("quality_gate", node_quality_gate)
    g.set_entry_point("discover")
    g.add_edge("discover", "match")
    g.add_edge("match", "quality_gate")
    g.add_edge("quality_gate", END)
    return g.compile()
