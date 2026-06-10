"""Re-rank already-discovered jobs using the current search.yaml + matcher.

Use this after editing search.yaml (excluded_titles / excluded_industries /
weights) when you DON'T want to pay for full re-discovery + LLM tailoring.

Steps:
  1. Truncate the `matches` table (stale scores from prior runs).
  2. Pull every JobRow from the DB.
  3. Run `rank_v2(profile, search, jobs)` -> writes fresh `matches`.
  4. Optionally regenerate the digest.

Usage:
  python scripts/rerank.py --thread tight-v2 --top 20
"""

from __future__ import annotations

from pathlib import Path

import typer
from sqlalchemy import text

from pega_agent.config import ROOT
from pega_agent.db import get_engine
from pega_agent.digest import write_digest_from_db
from pega_agent.matcher.agent_v2 import rank_v2
from pega_agent.models import JobPosting
from pega_agent.profile.agent import load_profile
from pega_agent.search.loader import load_search

app = typer.Typer()


@app.command()
def main(
    profile_path: Path = typer.Option(ROOT / "data" / "profile.yaml", "--profile", "-p"),
    search_path: Path = typer.Option(ROOT / "data" / "search.yaml", "--search", "-s"),
    out_dir: Path = typer.Option(ROOT / "data" / "digests", "--out", "-o"),
    thread: str = typer.Option("rerank", "--thread", "-t"),
    top_n: int = typer.Option(20, "--top"),
    no_digest: bool = typer.Option(False, "--no-digest"),
    watchlist_only: bool = typer.Option(False, "--watchlist-only", "-w"),
) -> None:
    profile = load_profile(profile_path)
    search = load_search(search_path)

    eng = get_engine()
    with eng.begin() as c:
        c.execute(text("DELETE FROM matches"))
        rows = c.execute(text("SELECT payload FROM jobs")).fetchall()
    import json

    jobs = [JobPosting(**json.loads(r[0]) if isinstance(r[0], str) else r[0]) for r in rows]
    typer.echo(f"Re-ranking {len(jobs)} cached jobs with current search.yaml…")

    kept, dropped = rank_v2(profile, search, jobs)
    typer.echo(
        f"  kept={len(kept)}  dropped={len(dropped)}  (dropped/{len(jobs)}={len(dropped) / max(1, len(jobs)):.0%})"
    )

    # Surface top drop reasons
    from collections import Counter

    top_reasons = Counter(dropped.values()).most_common(8)
    typer.echo("Top drop reasons:")
    for reason, n in top_reasons:
        typer.echo(f"  {n:>4}  {reason}")

    if no_digest:
        return
    path = write_digest_from_db(
        profile, search, out_dir, thread=thread, top_n=top_n, watchlist_only=watchlist_only
    )
    typer.echo(f"\nDigest: {path}")


if __name__ == "__main__":
    app()
