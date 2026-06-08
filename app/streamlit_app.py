"""Streamlit shell — minimal triage view for ranked matches.

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

from pega_agent.config import ROOT as PKG_ROOT  # noqa: E402
from pega_agent.db import load_briefs, load_jobs, load_matches  # noqa: E402
from pega_agent.graph import build_graph  # noqa: E402
from pega_agent.profile.agent import load_profile  # noqa: E402
from pega_agent.research.agent import research_company  # noqa: E402

st.set_page_config(page_title="Pega-en-Chile", layout="wide")
st.title("Pega-en-Chile")
st.caption("Agentic job search · Chile · human-in-the-loop")

profile_path = PKG_ROOT / "data" / "profile.yaml"

with st.sidebar:
    st.header("Run")
    location = st.text_input("Location", "Santiago, Chile")
    queries_raw = st.text_area("Queries (one per line)", "product manager\ngerente de producto")
    research_top_n = st.slider("Research top N companies", 0, 15, 5)
    if st.button("Discover + match + research", type="primary", use_container_width=True):
        if not profile_path.exists():
            st.error(f"No profile at {profile_path}. Run: pega profile-from-pdf ...")
        else:
            profile = load_profile(profile_path)
            graph = build_graph()
            with st.spinner("Running pipeline…"):
                graph.invoke(
                    {
                        "profile": profile,
                        "queries": [q.strip() for q in queries_raw.splitlines() if q.strip()],
                        "location": location,
                        "research_top_n": research_top_n,
                    }
                )
            st.success("Done.")

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

tab_matches, tab_jobs, tab_briefs = st.tabs(["Top matches", "All jobs", "Company briefs"])

with tab_matches:
    matches = load_matches(limit=50)
    if not matches:
        st.info("No matches yet. Run the pipeline from the sidebar.")
    else:
        df = pd.DataFrame([m.model_dump() for m in matches])
        st.dataframe(df, use_container_width=True, hide_index=True)

with tab_jobs:
    jobs = load_jobs(limit=200)
    if not jobs:
        st.info("No jobs in the local DB yet.")
    else:
        df = pd.DataFrame([j.model_dump() for j in jobs])
        cols = ["source", "title", "company", "location", "url", "posted_at"]
        st.dataframe(df[cols], use_container_width=True, hide_index=True)

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
