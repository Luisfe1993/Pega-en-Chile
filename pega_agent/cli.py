from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from pega_agent.config import ROOT
from pega_agent.db import load_matches
from pega_agent.graph import build_graph
from pega_agent.llm import has_llm
from pega_agent.profile.agent import (
    bootstrap_profile_from_text,
    extract_pdf_text,
    extract_profile_with_llm,
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
    no_llm: bool = typer.Option(
        False, "--no-llm", help="Force the heuristic seed even if an LLM key is configured."
    ),
) -> None:
    """Seed a profile.yaml from a PDF resume. Uses LLM extraction when available."""
    text = extract_pdf_text(pdf)
    if not no_llm and has_llm():
        with console.status("Extracting profile with LLM…"):
            profile = extract_profile_with_llm(name=name, text=text)
        mode = "LLM"
    else:
        profile = bootstrap_profile_from_text(name=name, text=text)
        mode = "heuristic"
    save_profile(profile, out)
    console.print(f"[green]✓[/green] wrote {out} ({mode})")
    if mode == "heuristic":
        console.print(
            "[yellow]next:[/yellow] open the file and fill in target_roles, target_sectors, "
            "skills and target_min_comp_clp."
        )


@app.command("run")
def run(
    profile_path: Path = typer.Option(DEFAULT_PROFILE_PATH, "--profile", "-p"),
    location: str = typer.Option("Santiago, Chile", "--location", "-l"),
    queries: list[str] = typer.Option(None, "--query", "-q"),
    research_top_n: int = typer.Option(5, "--research", help="Research top N companies"),
) -> None:
    """End-to-end: discover → match → research → quality-gate (stub)."""
    profile = load_profile(profile_path)
    graph = build_graph()
    final = graph.invoke(
        {
            "profile": profile,
            "queries": queries or profile.target_roles or ["product manager"],
            "location": location,
            "research_top_n": research_top_n,
        }
    )
    console.print(
        f"[green]✓[/green] approved {len(final.get('approved_ids', []))} top jobs · "
        f"{len(final.get('briefs', []))} company briefs"
    )


@app.command("research")
def research_cmd(
    company: str = typer.Argument(..., help="Company name to research"),
    no_cache: bool = typer.Option(False, "--no-cache", help="Bypass the SQLite cache"),
) -> None:
    """Generate (or fetch cached) `CompanyBrief` for one company."""
    from pega_agent.research.agent import research_company

    brief = research_company(company, use_cache=not no_cache)
    console.print(f"[bold]{brief.company}[/bold] — {brief.sector or '?'} · {brief.size or '?'}")
    console.print(brief.what_they_do)
    if brief.why_role_exists:
        console.print(f"[yellow]why role exists:[/yellow] {brief.why_role_exists}")
    if brief.recent_news:
        console.print("[bold]news[/bold]")
        for n in brief.recent_news:
            console.print(f"  • {n}")
    if brief.talking_points:
        console.print("[bold]talking points[/bold]")
        for p in brief.talking_points:
            console.print(f"  • {p}")
    if brief.red_flags:
        console.print("[red bold]red flags[/red bold]")
        for r in brief.red_flags:
            console.print(f"  ⚠ {r}")


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
