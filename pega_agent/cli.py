from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from pega_agent.config import ROOT
from pega_agent.db import load_approvals, load_matches
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
DEFAULT_THREAD = "current"


def _thread_cfg(thread: str) -> dict:
    return {"configurable": {"thread_id": thread}}


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
    tailor_top_n: int = typer.Option(3, "--tailor", help="Tailor CV + cover for top N jobs"),
    thread: str = typer.Option(DEFAULT_THREAD, "--thread", "-t", help="Run thread id"),
) -> None:
    """End-to-end pipeline. Pauses at the Quality Gate awaiting human review."""
    profile = load_profile(profile_path)
    graph = build_graph()
    state = graph.invoke(
        {
            "profile": profile,
            "queries": queries or profile.target_roles or ["product manager"],
            "location": location,
            "research_top_n": research_top_n,
            "tailor_top_n": tailor_top_n,
        },
        config=_thread_cfg(thread),
    )
    if "__interrupt__" in state:
        ints = state["__interrupt__"]
        ints_payload = ints[0].value if ints else {}
        console.print(
            f"[yellow]⏸ paused at Quality Gate[/yellow] · "
            f"{len(ints_payload.get('tailored', []))} tailored CVs · "
            f"{len(ints_payload.get('cover_letters', []))} cover letters · "
            f"{len(ints_payload.get('outreach', []))} outreach drafts"
        )
        console.print(
            f"  review and approve in Streamlit ([cyan]streamlit run app/streamlit_app.py[/cyan])\n"
            f"  or via CLI: [cyan]pega resume --thread {thread} --approve-all[/cyan]"
        )
    else:
        console.print(
            f"[green]✓[/green] approved {len(state.get('approved_ids', []))} top jobs · "
            f"{len(state.get('briefs', []))} company briefs"
        )


@app.command("resume")
def resume(
    thread: str = typer.Option(DEFAULT_THREAD, "--thread", "-t"),
    approve_all: bool = typer.Option(
        False, "--approve-all", help="Approve every pending artifact (for testing)."
    ),
) -> None:
    """Resume a paused run by feeding decisions into the Quality Gate."""
    from langgraph.types import Command

    graph = build_graph()
    snapshot = graph.get_state(config=_thread_cfg(thread))
    if not snapshot.next:
        console.print("[yellow]No pending interrupt on this thread.[/yellow]")
        return

    pending = snapshot.tasks[0].interrupts[0].value if snapshot.tasks else {}
    if not approve_all:
        console.print(
            "[red]No decisions provided.[/red] Pass --approve-all (testing) or use Streamlit."
        )
        return

    decisions = []
    for cv in pending.get("tailored", []):
        decisions.append({"job_id": cv["job_id"], "artifact": "tailored_cv", "status": "approved"})
    for cl in pending.get("cover_letters", []):
        decisions.append({"job_id": cl["job_id"], "artifact": "cover_letter", "status": "approved"})
    for o in pending.get("outreach", []):
        decisions.append({"job_id": o["job_id"], "artifact": "outreach", "status": "approved"})

    state = graph.invoke(Command(resume=decisions), config=_thread_cfg(thread))
    console.print(
        f"[green]✓[/green] resumed · approved {len(state.get('approved_ids', []))} jobs"
    )


@app.command("approvals")
def approvals_cmd(status: str = typer.Option(None, "--status", "-s")) -> None:
    """List approval decisions recorded in the DB."""
    rows = load_approvals(status=status)
    t = Table(title=f"Approvals ({status or 'all'})")
    t.add_column("decided_at")
    t.add_column("job_id")
    t.add_column("artifact")
    t.add_column("status")
    for r in rows:
        t.add_row(r.decided_at.isoformat(timespec="seconds"), r.job_id, r.artifact, r.status)
    console.print(t)


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
