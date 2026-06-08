"""Streamlit shell — triage view + Quality Gate approval queue.

Run:  streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# allow `streamlit run app/streamlit_app.py` without installing the package
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from langgraph.types import Command  # noqa: E402

from pega_agent.config import ROOT as PKG_ROOT  # noqa: E402
from pega_agent.db import (  # noqa: E402
    load_approvals,
    load_briefs,
    load_jobs,
    load_matches,
)
from pega_agent.graph import build_graph  # noqa: E402
from pega_agent.profile.agent import load_profile  # noqa: E402
from pega_agent.research.agent import research_company  # noqa: E402

st.set_page_config(page_title="Pega-en-Chile", layout="wide")
st.title("Pega-en-Chile")
st.caption("Agentic job search · Chile · human-in-the-loop")

profile_path = PKG_ROOT / "data" / "profile.yaml"
THREAD = st.session_state.setdefault("thread_id", "current")


def _thread_cfg() -> dict:
    return {"configurable": {"thread_id": THREAD}}


@st.cache_resource(show_spinner=False)
def _graph():
    return build_graph()


def _pending_artifacts() -> dict | None:
    """Returns the interrupt payload if the graph is paused, else None."""
    snap = _graph().get_state(config=_thread_cfg())
    if not snap.tasks:
        return None
    for task in snap.tasks:
        for it in task.interrupts:
            return it.value
    return None


# ---------- sidebar ------------------------------------------------------

with st.sidebar:
    st.header("Run")
    location = st.text_input("Location", "Santiago, Chile")
    queries_raw = st.text_area("Queries (one per line)", "product manager\ngerente de producto")
    research_top_n = st.slider("Research top N companies", 0, 15, 5)
    tailor_top_n = st.slider("Tailor + outreach top N", 0, 10, 3)
    if st.button("Discover → match → research → tailor → outreach", type="primary", use_container_width=True):
        if not profile_path.exists():
            st.error(f"No profile at {profile_path}. Run: pega profile-from-pdf …")
        else:
            profile = load_profile(profile_path)
            with st.spinner("Running pipeline…"):
                _graph().invoke(
                    {
                        "profile": profile,
                        "queries": [q.strip() for q in queries_raw.splitlines() if q.strip()],
                        "location": location,
                        "research_top_n": research_top_n,
                        "tailor_top_n": tailor_top_n,
                    },
                    config=_thread_cfg(),
                )
            st.success("Pipeline ran. If drafts exist, see the Approval Queue tab.")

    st.divider()
    st.subheader("Ad-hoc research")
    target_co = st.text_input("Company name")
    if st.button("Research company", use_container_width=True) and target_co:
        with st.spinner(f"Researching {target_co}…"):
            try:
                brief = research_company(target_co)
                st.success(f"Brief ready for {brief.company}")
            except Exception as e:
                st.error(str(e))

# ---------- tabs ---------------------------------------------------------

tab_queue, tab_matches, tab_jobs, tab_briefs, tab_approvals = st.tabs(
    ["⏸ Approval Queue", "Top matches", "All jobs", "Company briefs", "Approvals log"]
)

# ---------- Approval Queue tab ------------------------------------------

with tab_queue:
    pending = _pending_artifacts()
    if not pending:
        st.info(
            "No paused run on this thread. Click the big button on the left to start one."
        )
    else:
        tailored = pending.get("tailored", [])
        covers = pending.get("cover_letters", [])
        outs = pending.get("outreach", [])
        st.subheader(
            f"{len(tailored)} CVs · {len(covers)} cover letters · {len(outs)} outreach drafts pending"
        )

        decisions: list[dict] = []

        def _decision_block(
            artifact: str, job_id: str, default_body: str, key_prefix: str
        ) -> None:
            cols = st.columns([4, 1])
            with cols[0]:
                body = st.text_area(
                    "Body (editable)",
                    value=default_body,
                    height=180,
                    key=f"{key_prefix}_body",
                )
            with cols[1]:
                status = st.radio(
                    "Decision",
                    ["approved", "edited", "rejected"],
                    key=f"{key_prefix}_status",
                    horizontal=False,
                )
            decisions.append(
                {
                    "job_id": job_id,
                    "artifact": artifact,
                    "status": status,
                    "edited_body": body if status == "edited" else None,
                }
            )

        for cv in tailored:
            with st.expander(f"📄 CV · {cv['job_id']} · {cv.get('language', '?')}"):
                st.markdown(f"**Headline:** {cv['headline']}")
                st.markdown(f"**Summary:** {cv['summary']}")
                bullets_md = "\n".join(
                    f"- *{b['company']}* — {b['rephrased']}" for b in cv.get("bullets", [])
                )
                _decision_block("tailored_cv", cv["job_id"], bullets_md, f"cv_{cv['job_id']}")

        for cl in covers:
            with st.expander(f"✉️ Cover letter · {cl['job_id']} · {cl.get('language', '?')}"):
                _decision_block(
                    "cover_letter", cl["job_id"], cl["body"], f"cl_{cl['job_id']}"
                )

        for o in outs:
            with st.expander(
                f"💬 Outreach · {o['job_id']} · {o['channel']} · {o['register']}"
            ):
                if o.get("referral_path"):
                    rp = o["referral_path"]
                    st.caption(
                        f"Suggested intro: **{rp['contact_name']}** "
                        f"({rp.get('relationship') or 'relationship n/a'}) — "
                        f"confidence {rp.get('confidence', 0):.0%}"
                    )
                _decision_block("outreach", o["job_id"], o["body"], f"out_{o['job_id']}")

        st.divider()
        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("✅ Submit decisions", type="primary", use_container_width=True):
                with st.spinner("Resuming graph…"):
                    state = _graph().invoke(
                        Command(resume=decisions), config=_thread_cfg()
                    )
                st.success(
                    f"Done. Approved {len(state.get('approved_ids', []))} jobs."
                )
                st.rerun()
        with c2:
            if st.button("✅ Approve ALL pending", use_container_width=True):
                approve_all = [
                    {"job_id": d["job_id"], "artifact": d["artifact"], "status": "approved"}
                    for d in decisions
                ]
                with st.spinner("Resuming graph…"):
                    state = _graph().invoke(
                        Command(resume=approve_all), config=_thread_cfg()
                    )
                st.success(
                    f"Done. Approved {len(state.get('approved_ids', []))} jobs."
                )
                st.rerun()
        with c3:
            if st.button("❌ Reject ALL pending", use_container_width=True):
                reject_all = [
                    {"job_id": d["job_id"], "artifact": d["artifact"], "status": "rejected"}
                    for d in decisions
                ]
                with st.spinner("Resuming graph…"):
                    _graph().invoke(Command(resume=reject_all), config=_thread_cfg())
                st.success("Rejected.")
                st.rerun()

# ---------- Top matches tab ---------------------------------------------

with tab_matches:
    matches = load_matches(limit=50)
    if not matches:
        st.info("No matches yet. Run the pipeline from the sidebar.")
    else:
        df = pd.DataFrame([m.model_dump() for m in matches])
        st.dataframe(df, use_container_width=True, hide_index=True)

# ---------- All jobs tab -------------------------------------------------

with tab_jobs:
    jobs = load_jobs(limit=200)
    if not jobs:
        st.info("No jobs in the local DB yet.")
    else:
        df = pd.DataFrame([j.model_dump() for j in jobs])
        cols = ["source", "title", "company", "location", "url", "posted_at"]
        st.dataframe(df[cols], use_container_width=True, hide_index=True)

# ---------- Company briefs tab ------------------------------------------

with tab_briefs:
    briefs = load_briefs(limit=50)
    if not briefs:
        st.info("No company briefs yet. Run the pipeline or use the ad-hoc box.")
    else:
        for b in briefs:
            with st.expander(f"**{b.company}** — {b.sector or ''} · {b.size or ''}"):
                st.write(b.what_they_do)
                if b.headquarters:
                    st.caption(f"HQ: {b.headquarters}")
                if b.why_role_exists:
                    st.markdown(f"**Why this role exists:** {b.why_role_exists}")
                if b.recent_news:
                    st.markdown("**Recent news**")
                    for n in b.recent_news:
                        st.markdown(f"- {n}")
                if b.talking_points:
                    st.markdown("**Talking points**")
                    for p in b.talking_points:
                        st.markdown(f"- {p}")
                if b.red_flags:
                    st.markdown("**Red flags**")
                    for r in b.red_flags:
                        st.markdown(f"- ⚠️ {r}")
                if b.sources:
                    st.caption("Sources: " + " · ".join(b.sources[:5]))

# ---------- Approvals log tab -------------------------------------------

with tab_approvals:
    rows = load_approvals(limit=200)
    if not rows:
        st.info("No approvals recorded yet.")
    else:
        df = pd.DataFrame([r.model_dump() for r in rows])
        st.dataframe(df, use_container_width=True, hide_index=True)
