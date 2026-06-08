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
from pega_agent.db import load_jobs, load_matches  # noqa: E402
from pega_agent.graph import build_graph  # noqa: E402
from pega_agent.profile.agent import load_profile  # noqa: E402

st.set_page_config(page_title="Pega-en-Chile", layout="wide")
st.title("Pega-en-Chile")
st.caption("Agentic job search · Chile · human-in-the-loop")

profile_path = PKG_ROOT / "data" / "profile.yaml"

with st.sidebar:
    st.header("Run")
    location = st.text_input("Location", "Santiago, Chile")
    queries_raw = st.text_area("Queries (one per line)", "product manager\ngerente de producto")
    if st.button("Discover + match", type="primary", use_container_width=True):
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
                    }
                )
            st.success("Done.")

tab_matches, tab_jobs = st.tabs(["Top matches", "All jobs"])

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
