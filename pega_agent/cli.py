from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from pega_agent.config import ROOT
from pega_agent.db import load_matches
from pega_agent.graph import build_graph
from pega_agent.profile.agent import (
    bootstrap_profile_from_text,
    extract_pdf_text,
    load_profile,
    save_profile,
)

app = typer.Typer(help="Pega-en-Chile CLI")
console = Console()

DEFAULT_PROFILE_PATH = ROOT / "data" / "profile.yaml"


@app.command("profile-from-pdf")
def profile_from_pdf(
    pdf: Path = typer.Argument(..., exists=True, readable=True),
    name: str = typer.Option(..., "--name", "-n", help="Your full name"),
    out: Path = typer.Option(DEFAULT_PROFILE_PATH, "--out", "-o"),
) -> None:
    """Seed a profile.yaml from a PDF resume (heuristic; refine by hand)."""
    text = extract_pdf_text(pdf)
    profile = bootstrap_profile_from_text(name=name, text=text)
    save_profile(profile, out)
    console.print(f"[green]✓[/green] wrote {out}")
    console.print(
        "[yellow]next:[/yellow] open the file and fill in target_roles, target_sectors, "
        "skills and target_min_comp_clp."
    )


@app.command("run")
def run(
    profile_path: Path = typer.Option(DEFAULT_PROFILE_PATH, "--profile", "-p"),
    location: str = typer.Option("Santiago, Chile", "--location", "-l"),
    queries: list[str] = typer.Option(None, "--query", "-q"),
) -> None:
    """End-to-end: discover → match → quality-gate (stub)."""
    profile = load_profile(profile_path)
    graph = build_graph()
    final = graph.invoke(
        {
            "profile": profile,
            "queries": queries or profile.target_roles or ["product manager"],
            "location": location,
        }
    )
    console.print(f"[green]✓[/green] approved {len(final.get('approved_ids', []))} top jobs")


@app.command("top")
def top(limit: int = 20) -> None:
    """Show top-ranked matches from the local DB."""
    matches = load_matches(limit=limit)
    t = Table(title="Top matches", show_lines=False)
    t.add_column("score", justify="right")
    t.add_column("job_id")
    t.add_column("rationale")
    for m in matches:
        t.add_row(f"{m.score:.1f}", m.job_id, m.rationale)
    console.print(t)


if __name__ == "__main__":
    app()
