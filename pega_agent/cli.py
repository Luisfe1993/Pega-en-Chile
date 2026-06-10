from __future__ import annotations

from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from pega_agent.config import ROOT
from pega_agent.db import load_approvals, load_brief, load_job, load_matches
from pega_agent.digest import write_digest_from_db
from pega_agent.graph import build_graph
from pega_agent.llm import has_llm
from pega_agent.profile.agent import (
    bootstrap_profile_from_text,
    extract_pdf_text,
    extract_profile_with_llm,
    load_profile,
    save_profile,
)
from pega_agent.search.loader import load_search

app = typer.Typer(help="Pega-en-Chile CLI")
console = Console()

DEFAULT_PROFILE_PATH = ROOT / "data" / "profile.yaml"
DEFAULT_SEARCH_PATH = ROOT / "data" / "search.yaml"
DEFAULT_DIGEST_DIR = ROOT / "data" / "digests"
DEFAULT_EXPORT_DIR = ROOT / "data" / "exports"
DEFAULT_RECRUITERS_PATH = ROOT / "data" / "recruiters.yaml"
DEFAULT_LINKEDIN_DIR = ROOT / "data" / "linkedin_export"
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
    search_path: Path = typer.Option(DEFAULT_SEARCH_PATH, "--search", "-s"),
    location: str = typer.Option("Santiago, Chile", "--location", "-l"),
    queries: list[str] = typer.Option(None, "--query", "-q"),
    research_top_n: int = typer.Option(5, "--research", help="Research top N companies"),
    tailor_top_n: int = typer.Option(3, "--tailor", help="Tailor CV + cover for top N jobs"),
    thread: str = typer.Option(DEFAULT_THREAD, "--thread", "-t", help="Run thread id"),
) -> None:
    """End-to-end pipeline. Pauses at the Quality Gate awaiting human review."""
    profile = load_profile(profile_path)
    search = load_search(search_path)
    graph = build_graph()
    state = graph.invoke(
        {
            "profile": profile,
            "search": search,
            "queries": queries or search.queries or ["product manager"],
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
    if state.get("digest_path"):
        console.print(f"[green]✓ digest[/green] [cyan]{state['digest_path']}[/cyan]")


@app.command("digest")
def digest_cmd(
    profile_path: Path = typer.Option(DEFAULT_PROFILE_PATH, "--profile", "-p"),
    search_path: Path = typer.Option(DEFAULT_SEARCH_PATH, "--search", "-s"),
    out_dir: Path = typer.Option(DEFAULT_DIGEST_DIR, "--out", "-o"),
    top_n: int = typer.Option(15, "--top", help="How many ranked matches to include."),
    thread: str = typer.Option("manual", "--thread", "-t"),
    watchlist_only: bool = typer.Option(
        False,
        "--watchlist-only",
        "-w",
        help="Only include jobs whose company is on the watchlist in data/recruiters.yaml.",
    ),
) -> None:
    """Regenerate the Markdown digest from the current DB state (no new discovery)."""
    profile = load_profile(profile_path)
    search = load_search(search_path)
    path = write_digest_from_db(
        profile,
        search,
        out_dir,
        thread=thread,
        top_n=top_n,
        watchlist_only=watchlist_only,
    )
    console.print(f"[green]✓[/green] {path}")


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


@app.command("show")
def show_cmd(
    job_id: str = typer.Argument(..., help="job_id from `pega top` or the digest"),
    out_dir: Path = typer.Option(DEFAULT_EXPORT_DIR, "--out", "-o", help="Where to write the .md files"),
) -> None:
    """Export the tailored CV + cover letter + brief for a job as Markdown files."""
    from pega_agent.db import load_cover_letter, load_tailored_cv

    job = load_job(job_id)
    if not job:
        console.print(f"[red]No job in DB with id {job_id}.[/red] Try `pega top` to list them.")
        raise typer.Exit(1)

    cv = load_tailored_cv(job_id)
    cl = load_cover_letter(job_id)
    brief = load_brief(job.company)

    if not (cv or cl or brief):
        console.print(
            f"[yellow]Nothing tailored yet for {job.company} · {job.title}.[/yellow]\n"
            f"Run: [bold]pega run --research 5 --tailor 3[/bold] to generate artifacts."
        )
        raise typer.Exit(0)

    safe_company = "".join(c if c.isalnum() or c in "-_" else "_" for c in job.company)[:40]
    target = out_dir / f"{safe_company}__{job_id[:8]}"
    target.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []

    if cv:
        lines = [
            f"# {cv.headline}",
            "",
            f"_Tailored for: **{job.company}** — {job.title}_",
            "",
            "## Summary",
            "",
            cv.summary,
            "",
            "## Experience highlights",
            "",
        ]
        for b in sorted(cv.bullets, key=lambda x: -x.emphasis):
            lines.append(f"- {b.rephrased}")
            if b.rationale:
                lines.append(f"  - _why_: {b.rationale}")
        if cv.skills_top:
            lines += ["", "## Top skills", "", ", ".join(cv.skills_top)]
        if cv.notes:
            lines += ["", "## Notes", "", cv.notes]
        path = target / "cv.md"
        path.write_text("\n".join(lines), encoding="utf-8")
        written.append(path)

        # Also produce a .docx that mirrors the user's resume template, if any.
        from pega_agent.config import settings

        template = Path(settings.resume_template_path)
        if template.exists():
            from pega_agent.resume_writer import render_resume_docx

            docx_path = render_resume_docx(cv, template, target / "cv.docx")
            written.append(docx_path)

    if cl:
        lines = [
            f"**To:** {cl.recipient or 'Hiring Manager'}",
            f"**Subject:** {cl.subject or f'Application — {job.title}'}",
            "",
            cl.body,
        ]
        path = target / "cover-letter.md"
        path.write_text("\n".join(lines), encoding="utf-8")
        written.append(path)

    if brief:
        b_lines = [f"# {brief.company}", "", brief.what_they_do]
        if brief.sector or brief.size or brief.headquarters:
            meta = " · ".join(x for x in [brief.sector, brief.size, brief.headquarters] if x)
            b_lines += ["", f"_{meta}_"]
        if brief.why_role_exists:
            b_lines += ["", "## Why this role exists", "", brief.why_role_exists]
        if brief.talking_points:
            b_lines += ["", "## Talking points"] + [f"- {t}" for t in brief.talking_points]
        if brief.recent_news:
            b_lines += ["", "## Recent news"] + [f"- {n}" for n in brief.recent_news]
        if brief.red_flags:
            b_lines += ["", "## Red flags"] + [f"- {r}" for r in brief.red_flags]
        if brief.sources:
            b_lines += ["", "## Sources"] + [f"- {s}" for s in brief.sources]
        path = target / "company-brief.md"
        path.write_text("\n".join(b_lines) + "\n", encoding="utf-8")
        written.append(path)

    console.print(f"[green]✓[/green] {job.company} · {job.title}")
    console.print(f"  → {target}")
    for p in written:
        console.print(f"    • {p.name}")
    if not cv:
        console.print("  [yellow]·[/yellow] no tailored CV yet (run with --tailor N)")
    if not cl:
        console.print("  [yellow]·[/yellow] no cover letter yet (run with --tailor N)")
    if not brief:
        console.print("  [yellow]·[/yellow] no company brief yet (run with --research N)")


@app.command("tailor")
def tailor_cmd(
    job_id: str = typer.Argument(..., help="job_id from `pega top` or the digest"),
    profile_path: Path = typer.Option(DEFAULT_PROFILE_PATH, "--profile", "-p"),
    force: bool = typer.Option(False, "--force", help="Re-tailor even if cached"),
) -> None:
    """Research + tailor CV + draft cover letter for one job. Cached unless --force."""
    from pega_agent.db import load_cover_letter, load_tailored_cv, save_brief
    from pega_agent.research.agent import research_company
    from pega_agent.tailor.agent import draft_cover_letter, tailor_cv

    if not has_llm():
        console.print("[red]LLM key required.[/red] Set OPENAI_API_KEY or AZURE_OPENAI_*.")
        raise typer.Exit(1)
    job = load_job(job_id)
    if not job:
        console.print(f"[red]No job in DB with id {job_id}.[/red]")
        raise typer.Exit(1)
    profile = load_profile(profile_path)

    brief = load_brief(job.company)
    if not brief:
        console.print(f"  → researching {job.company} ...")
        brief = research_company(job.company, posting=job)
        save_brief(brief)

    cv = load_tailored_cv(job_id) if not force else None
    if not cv:
        console.print(f"  → tailoring CV for {job.title} ...")
        cv = tailor_cv(profile, job, brief)

    cl = load_cover_letter(job_id) if not force else None
    if not cl:
        console.print(f"  → drafting cover letter ...")
        cl = draft_cover_letter(profile, job, cv, brief)

    console.print(
        f"[green]Done[/green] {job.company} · {job.title}  "
        f"(brief · cv · cl saved). Export with: pega show {job_id}"
    )


@app.command("interview-prep")
def interview_prep_cmd(
    job_id: str = typer.Argument(..., help="job_id of an approved job"),
    profile_path: Path = typer.Option(DEFAULT_PROFILE_PATH, "--profile", "-p"),
) -> None:
    """Generate an InterviewPrepPack (STAR + case + questions) for a job."""
    from pega_agent.db import load_cover_letter, load_tailored_cv
    from pega_agent.interview.agent import generate_prep_pack

    if not has_llm():
        console.print("[red]LLM key required.[/red] Set OPENAI_API_KEY or ANTHROPIC_API_KEY.")
        raise typer.Exit(1)
    job = load_job(job_id)
    if not job:
        console.print(f"[red]No job in DB with id {job_id}.[/red]")
        raise typer.Exit(1)
    profile = load_profile(profile_path)
    brief = load_brief(job.company)
    cv = load_tailored_cv(job_id)
    _ = load_cover_letter(job_id)  # touch so the cache shows it; unused here
    with console.status(f"Generating prep pack for {job.company} · {job.title}…"):
        pack = generate_prep_pack(profile, job, brief=brief, cv=cv)
    console.print(f"[bold]Company angle[/bold]\n{pack.company_angle}\n")
    console.print(f"[bold]STAR stories ({len(pack.star_stories)})[/bold]")
    for s in pack.star_stories:
        console.print(f"  • [{s.theme}] {s.title} — source: {s.source_company}")
    console.print(f"[bold]Case warmups ({len(pack.case_warmups)})[/bold]")
    for c in pack.case_warmups:
        console.print(f"  • {c.prompt[:120]}…")
    console.print("[bold]Questions to ask[/bold]")
    for q in pack.questions_to_ask:
        console.print(f"  • {q}")
    console.print("[bold]Likely questions[/bold]")
    for q in pack.likely_questions:
        console.print(f"  • {q}")
    console.print(f"\n[green]✓[/green] saved prep pack for job {job_id}")


@app.command("negotiate")
def negotiate_cmd(
    job_id: str = typer.Argument(..., help="job_id of an approved job"),
    offer: int = typer.Option(..., "--offer", help="Current offer base in CLP gross monthly"),
    variable_pct: float | None = typer.Option(None, "--variable", help="Variable as % of base"),
    competing: int | None = typer.Option(None, "--competing", help="Competing offer in CLP gross monthly"),
    profile_path: Path = typer.Option(DEFAULT_PROFILE_PATH, "--profile", "-p"),
) -> None:
    """Generate a CLP-anchored negotiation plan and counter-offer email draft."""
    from pega_agent.negotiation.agent import negotiate

    if not has_llm():
        console.print("[red]LLM key required.[/red] Set OPENAI_API_KEY or ANTHROPIC_API_KEY.")
        raise typer.Exit(1)
    job = load_job(job_id)
    if not job:
        console.print(f"[red]No job in DB with id {job_id}.[/red]")
        raise typer.Exit(1)
    profile = load_profile(profile_path)
    brief = load_brief(job.company)
    with console.status(f"Drafting negotiation for {job.company} · {job.title}…"):
        neg = negotiate(
            profile,
            job,
            offer_base_clp=offer,
            offer_variable_pct=variable_pct,
            competing_offer_clp=competing,
            brief=brief,
        )
    bench = neg.benchmark
    console.print(
        f"[bold]Benchmark[/bold] · {bench.role} · {bench.seniority} · "
        f"low={bench.base_low_clp:,} mid={bench.base_mid_clp:,} high={bench.base_high_clp:,} CLP/mo"
    )
    console.print(f"[bold]Target[/bold] {neg.target_base_clp:,} CLP/mo · [bold]Walk-away[/bold] {neg.walk_away_clp:,} CLP/mo")
    console.print(f"[bold]Rationale[/bold] {neg.rationale}\n")
    console.print("[bold]Levers[/bold]")
    for lv in neg.levers_to_negotiate:
        console.print(f"  • {lv}")
    if neg.counter_email_subject:
        console.print(f"\n[bold]Subject:[/bold] {neg.counter_email_subject}")
    console.print(f"\n{neg.counter_email_body}")
    console.print(f"\n[green]✓[/green] saved negotiation draft for job {job_id}")


# ---------- Recruiter intro ----------------------------------------------


@app.command("recruiter-intro")
def recruiter_intro_cmd(
    job_id: str = typer.Argument(..., help="job_id from `pega top` / the digest"),
    firm: str = typer.Option(
        ...,
        "--firm",
        "-f",
        help="Search firm name (e.g. 'Spencer Stuart') OR warm contact firm.",
    ),
    contact: str | None = typer.Option(
        None, "--contact", "-c", help="Specific recruiter/contact first name, if known."
    ),
    profile_path: Path = typer.Option(DEFAULT_PROFILE_PATH, "--profile", "-p"),
    recruiters_path: Path = typer.Option(
        DEFAULT_RECRUITERS_PATH, "--recruiters", "-r"
    ),
    out_dir: Path = typer.Option(DEFAULT_EXPORT_DIR, "--out", "-o"),
) -> None:
    """Draft a bilingual (ES + EN) intro message to a recruiter about a job."""
    from pega_agent.recruiter import draft_recruiter_intro, load_recruiters_yaml

    if not has_llm():
        console.print("[red]LLM key required.[/red] Set OPENAI_API_KEY / GITHUB_TOKEN.")
        raise typer.Exit(1)
    job = load_job(job_id)
    if not job:
        console.print(f"[red]No job in DB with id {job_id}.[/red]")
        raise typer.Exit(1)
    profile = load_profile(profile_path)
    brief = load_brief(job.company)
    recruiters = load_recruiters_yaml(recruiters_path)
    with console.status(f"Drafting recruiter intro for {firm} → {job.company} · {job.title}…"):
        intro = draft_recruiter_intro(
            profile,
            job,
            firm=firm,
            contact_name=contact,
            brief=brief,
            recruiters_data=recruiters,
        )

    safe_company = "".join(c if c.isalnum() or c in "-_" else "_" for c in job.company)[:40]
    safe_firm = "".join(c if c.isalnum() or c in "-_" else "_" for c in firm)[:40]
    target = out_dir / f"{safe_company}__{job_id[:8]}"
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"recruiter-intro__{safe_firm}.md"

    addressee = contact or f"{firm} team"
    lines = [
        f"# Recruiter intro — {firm}",
        "",
        f"_For: **{job.company}** — {job.title}_",
        f"_To: {addressee}_",
        "",
        "## Español (formal)",
        "",
        f"**Asunto:** {intro.subject_es}",
        "",
        intro.body_es,
        "",
        "---",
        "",
        "## English",
        "",
        f"**Subject:** {intro.subject_en}",
        "",
        intro.body_en,
    ]
    if intro.rationale:
        lines += ["", "---", "", f"_Why this angle:_ {intro.rationale}"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    console.print(f"[green]✓[/green] {firm} → {job.company} · {job.title}")
    console.print(f"  → {path}")


# ---------- Outreach tracker --------------------------------------------

outreach_app = typer.Typer(help="Manual outreach log: who you contacted, when, status.")
app.add_typer(outreach_app, name="outreach")


def _short_id() -> str:
    import uuid

    return uuid.uuid4().hex[:8]


@outreach_app.command("add")
def outreach_add(
    contact: str = typer.Option(..., "--contact", "-c", help="Contact full name"),
    firm: str | None = typer.Option(None, "--firm", "-f", help="Firm / company"),
    job_id: str | None = typer.Option(None, "--job", "-j", help="Related job_id"),
    channel: str = typer.Option(
        "linkedin", "--channel", help="linkedin | email | phone | warm_intro | other"
    ),
    status: str = typer.Option(
        "sent", "--status", "-s", help="drafted | sent | replied | call_booked | rejected | ghosted"
    ),
    notes: str | None = typer.Option(None, "--notes", "-n"),
) -> None:
    """Log a new outbound touch (recruiter, hiring manager, warm contact)."""
    from pega_agent.db import save_outreach_log
    from pega_agent.models import OutreachLogEntry

    now = datetime.now()
    entry = OutreachLogEntry(
        id=_short_id(),
        contact_name=contact,
        firm=firm,
        job_id=job_id,
        channel=channel,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        sent_at=now if status in ("sent", "replied", "call_booked") else None,
        notes=notes,
        created_at=now,
        updated_at=now,
    )
    save_outreach_log(entry)
    console.print(f"[green]✓[/green] logged {entry.id} · {contact} ({status})")


@outreach_app.command("list")
def outreach_list(
    status: str | None = typer.Option(None, "--status", "-s"),
    firm: str | None = typer.Option(None, "--firm", "-f"),
    job_id: str | None = typer.Option(None, "--job", "-j"),
    limit: int = typer.Option(100, "--limit"),
) -> None:
    """List outreach entries, newest first."""
    from pega_agent.db import list_outreach_log

    rows = list_outreach_log(status=status, firm=firm, job_id=job_id, limit=limit)
    if not rows:
        console.print("[yellow]No outreach entries match.[/yellow]")
        return
    t = Table(title=f"Outreach ({len(rows)})")
    t.add_column("id")
    t.add_column("updated")
    t.add_column("contact")
    t.add_column("firm")
    t.add_column("job")
    t.add_column("ch")
    t.add_column("status")
    t.add_column("notes", overflow="fold", max_width=40)
    for r in rows:
        t.add_row(
            r.id,
            r.updated_at.strftime("%m-%d %H:%M"),
            r.contact_name,
            r.firm or "—",
            (r.job_id or "—")[:8],
            r.channel,
            r.status,
            (r.notes or "")[:80],
        )
    console.print(t)


@outreach_app.command("update")
def outreach_update(
    entry_id: str = typer.Argument(..., help="Short id from `pega outreach list`"),
    status: str | None = typer.Option(None, "--status", "-s"),
    notes: str | None = typer.Option(None, "--notes", "-n"),
    replied: bool = typer.Option(False, "--replied", help="Mark replied_at = now"),
    follow_up_days: int | None = typer.Option(
        None, "--follow-up-days", help="Set follow_up_at = now + N days"
    ),
) -> None:
    """Update status / notes on an outreach entry."""
    from datetime import timedelta

    from pega_agent.db import load_outreach_log, save_outreach_log

    entry = load_outreach_log(entry_id)
    if not entry:
        console.print(f"[red]No outreach entry with id {entry_id}.[/red]")
        raise typer.Exit(1)
    if status:
        entry.status = status  # type: ignore[assignment]
    if notes is not None:
        entry.notes = notes
    if replied:
        entry.replied_at = datetime.now()
        if entry.status in ("drafted", "sent"):
            entry.status = "replied"
    if follow_up_days is not None:
        entry.follow_up_at = datetime.now() + timedelta(days=follow_up_days)
    entry.updated_at = datetime.now()
    save_outreach_log(entry)
    console.print(f"[green]✓[/green] updated {entry_id} → {entry.status}")


@outreach_app.command("due")
def outreach_due(within_days: int = typer.Option(0, "--within-days", "-d")) -> None:
    """Show entries whose follow_up_at is on/before today (+within_days)."""
    from datetime import timedelta

    from pega_agent.db import list_outreach_log

    cutoff = datetime.now() + timedelta(days=within_days)
    rows = [
        r
        for r in list_outreach_log(limit=500)
        if r.follow_up_at and r.follow_up_at <= cutoff
        and r.status not in ("rejected", "call_booked")
    ]
    if not rows:
        console.print("[green]Nothing due.[/green]")
        return
    t = Table(title=f"Follow-ups due (≤ {within_days}d)")
    t.add_column("due")
    t.add_column("id")
    t.add_column("contact")
    t.add_column("firm")
    t.add_column("status")
    for r in sorted(rows, key=lambda x: x.follow_up_at):  # type: ignore[arg-type]
        t.add_row(
            r.follow_up_at.strftime("%m-%d"),  # type: ignore[union-attr]
            r.id,
            r.contact_name,
            r.firm or "—",
            r.status,
        )
    console.print(t)


# ---------- Contacts (LinkedIn export) -----------------------------------

contacts_app = typer.Typer(help="LinkedIn contacts: import export, match prospects, verify emails.")
app.add_typer(contacts_app, name="contacts")


@contacts_app.command("import")
def contacts_import(
    path: Path = typer.Option(
        DEFAULT_LINKEDIN_DIR, "--path", "-p",
        help="Directory containing LinkedIn export CSVs.",
    ),
) -> None:
    """Import Connections / Invitations / messages / Company Follows / Endorsements."""
    from pega_agent.contacts import import_linkedin_export
    if not path.exists():
        console.print(f"[red]Path not found:[/red] {path}")
        raise typer.Exit(1)
    console.print(f"[cyan]Importing from {path}…[/cyan]")
    counts = import_linkedin_export(path)
    from pega_agent.db import count_contacts
    t = Table(title="LinkedIn import")
    t.add_column("source")
    t.add_column("rows", justify="right")
    for k, v in counts.items():
        t.add_row(k, str(v))
    t.add_row("[bold]total contacts in DB[/bold]", f"[bold]{count_contacts()}[/bold]")
    console.print(t)


@contacts_app.command("verify")
def contacts_verify() -> None:
    """Run free verification (syntax + MX) on every contact email."""
    from pega_agent.contacts import verify_all_contact_emails
    counts = verify_all_contact_emails()
    if not counts:
        console.print("[yellow]No contacts with emails to verify.[/yellow]")
        return
    t = Table(title="Email verification")
    t.add_column("status")
    t.add_column("count", justify="right")
    for k, v in counts.items():
        t.add_row(k, str(v))
    console.print(t)


@contacts_app.command("match")
def contacts_match(
    top: int = typer.Option(30, "--top", help="How many top-match companies to include."),
    recruiters: Path = typer.Option(DEFAULT_RECRUITERS_PATH, "--recruiters"),
) -> None:
    """Show 1st-degree contacts at prospect companies (watchlist + top digest matches)."""
    from pega_agent.contacts import match_contacts_to_prospects
    from pega_agent.db import load_matches, load_job
    prospects: list[str] = []
    # 1) Watchlist (exec-search firms + their warm contacts)
    if recruiters.exists():
        from pega_agent.recruiter import load_recruiters_yaml
        cfg = load_recruiters_yaml(recruiters)
        for f in cfg.get("target_firms", []) or []:
            n = f.get("name")
            if n:
                prospects.append(n)
        for w in cfg.get("warm_contacts", []) or []:
            n = w.get("firm")
            if n and n not in prospects:
                prospects.append(n)
    # 2) Top digest match companies
    for ms in load_matches(limit=top):
        j = load_job(ms.job_id)
        if j and j.company and j.company not in prospects:
            prospects.append(j.company)
    matches = match_contacts_to_prospects(prospects)
    t = Table(title=f"Contacts at {len(matches)} prospect companies")
    t.add_column("company")
    t.add_column("# contacts", justify="right")
    t.add_column("top contact")
    for company, contacts in matches.items():
        top_c = contacts[0].full_name if contacts else "—"
        t.add_row(company, str(len(contacts)), top_c)
    console.print(t)


@contacts_app.command("plan")
def contacts_plan(
    top: int = typer.Option(30, "--top"),
    per_company: int = typer.Option(5, "--per-company"),
    recruiters: Path = typer.Option(DEFAULT_RECRUITERS_PATH, "--recruiters"),
    out: Path = typer.Option(
        DEFAULT_EXPORT_DIR / f"outreach-plan__{datetime.utcnow().strftime('%Y-%m-%d')}.md",
        "--out", "-o",
    ),
) -> None:
    """Render a tiered (A/B/C/D) outreach plan markdown report."""
    from pega_agent.contacts import match_contacts_to_prospects, render_outreach_plan
    from pega_agent.db import load_matches, load_job
    prospects: list[str] = []
    if recruiters.exists():
        from pega_agent.recruiter import load_recruiters_yaml
        cfg = load_recruiters_yaml(recruiters)
        for f in cfg.get("target_firms", []) or []:
            n = f.get("name")
            if n:
                prospects.append(n)
        for w in cfg.get("warm_contacts", []) or []:
            n = w.get("firm")
            if n and n not in prospects:
                prospects.append(n)
    for ms in load_matches(limit=top):
        j = load_job(ms.job_id)
        if j and j.company and j.company not in prospects:
            prospects.append(j.company)
    matches = match_contacts_to_prospects(prospects)
    report = render_outreach_plan(matches, top_n_per_company=per_company)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    console.print(f"[green]Wrote outreach plan to[/green] {out}")


@contacts_app.command("dm")
def contacts_dm(
    job_id: str = typer.Argument(..., help="Job id to anchor the DM to."),
    linkedin_url: str = typer.Argument(..., help="Contact's LinkedIn URL (must already be in DB)."),
) -> None:
    """Draft a short LinkedIn DM to a 1st-degree contact about a specific opening."""
    from pega_agent.contacts import draft_linkedin_dm
    from pega_agent.db import ContactRow, get_engine, load_job
    from sqlalchemy.orm import Session as _S

    job = load_job(job_id)
    if not job:
        console.print(f"[red]Job not found:[/red] {job_id}")
        raise typer.Exit(1)
    engine = get_engine()
    with _S(engine) as s:
        contact = s.get(ContactRow, linkedin_url)
    if not contact:
        console.print(f"[red]Contact not found in DB:[/red] {linkedin_url}")
        console.print("[yellow]Tip:[/yellow] run `pega contacts import` first.")
        raise typer.Exit(1)
    profile = load_profile(DEFAULT_PROFILE_PATH)
    if not has_llm():
        console.print("[red]LLM not configured — set OPENAI_API_KEY or equivalent.[/red]")
        raise typer.Exit(1)
    draft = draft_linkedin_dm(profile, job, contact)
    console.rule(f"[bold]LinkedIn DM → {contact.full_name} ({job.company})[/bold]")
    console.print("[bold cyan]ES[/bold cyan]")
    console.print(draft["body_es"])
    console.print()
    console.print("[bold cyan]EN[/bold cyan]")
    console.print(draft["body_en"])
    console.print()
    console.print(f"[dim]Paste into:[/dim] {contact.linkedin_url}")


@contacts_app.command("guess-email")
def contacts_guess_email(
    linkedin_url: str = typer.Argument(..., help="Contact's LinkedIn URL."),
    domain: str = typer.Option(..., "--domain", "-d", help="Company email domain (e.g. mastercard.com)."),
) -> None:
    """Try common email patterns for the contact + domain; MX-verify each."""
    from pega_agent.contacts import guess_and_verify_email
    from pega_agent.db import ContactRow, get_engine
    from sqlalchemy.orm import Session as _S

    engine = get_engine()
    with _S(engine) as s:
        contact = s.get(ContactRow, linkedin_url)
    if not contact:
        console.print(f"[red]Contact not found:[/red] {linkedin_url}")
        raise typer.Exit(1)
    email, status = guess_and_verify_email(contact, domain)
    if email:
        console.print(f"[green]Found[/green] {email}  ({status})")
        console.print(
            "[yellow]Note:[/yellow] MX-ok proves the domain accepts mail, NOT that this\n"
            "specific mailbox exists. Treat as a candidate; verify with a low-stakes\n"
            "first message before sending anything sensitive."
        )
    else:
        console.print(f"[yellow]No match[/yellow] — {status}")


# ---------- Pipeline (per-opportunity funnel) ---------------------------

pipeline_app = typer.Typer(help="Per-opportunity funnel view: where am I on each job?")
app.add_typer(pipeline_app, name="pipeline")

_STAGE_COLORS = {
    "discovered": "white",
    "researching": "cyan",
    "tailored": "cyan",
    "outreach_sent": "yellow",
    "reply_received": "green",
    "applied": "yellow",
    "screen_scheduled": "bold green",
    "onsite": "bold green",
    "offer": "bold magenta",
    "rejected": "red",
    "ghosted": "dim",
    "parked": "dim",
}


def _derive_stage_for_job(job_id: str) -> str:
    """Auto-derive the highest stage knowable from DB signals (no outreach send tracking yet)."""
    from pega_agent.db import (
        CompanyBriefRow,
        CoverLetterRow,
        OutreachLogRow,
        TailoredCVRow,
        get_engine,
        load_job,
    )
    from sqlalchemy.orm import Session as _S

    job = load_job(job_id)
    if not job:
        return "discovered"
    engine = get_engine()
    with _S(engine) as s:
        # outreach_log entries scoped to this job
        out_rows = s.query(OutreachLogRow).filter(OutreachLogRow.job_id == job_id).all()
        if any(r.status == "replied" for r in out_rows):
            return "reply_received"
        if any(r.status in ("sent", "followed_up") for r in out_rows):
            return "outreach_sent"
        if s.get(TailoredCVRow, job_id) and s.get(CoverLetterRow, job_id):
            return "tailored"
        if s.get(CompanyBriefRow, (job.company or "").lower()):
            return "researching"
    return "discovered"


@pipeline_app.command("sync")
def pipeline_sync(
    limit: int = typer.Option(100, "--limit", "-n", help="Max jobs to seed (top-scoring first)."),
) -> None:
    """Seed/refresh pipeline rows for top-scoring jobs from existing DB signals."""
    from pega_agent.db import load_matches, load_job, upsert_pipeline
    seeded = advanced = skipped = 0
    for ms in load_matches(limit=limit):
        j = load_job(ms.job_id)
        if not j:
            continue
        derived = _derive_stage_for_job(ms.job_id)
        before = None
        from pega_agent.db import get_pipeline
        existing = get_pipeline(ms.job_id)
        if existing:
            before = existing.stage
        upsert_pipeline(ms.job_id, stage=derived)
        if before is None:
            seeded += 1
        elif before != derived:
            advanced += 1
        else:
            skipped += 1
    console.print(
        f"[green]Sync done.[/green] seeded={seeded}  advanced={advanced}  unchanged={skipped}"
    )


@pipeline_app.command("view")
def pipeline_view(
    stage: str = typer.Option(None, "--stage", "-s", help="Filter to one stage."),
    active_only: bool = typer.Option(
        False, "--active", "-a", help="Hide rejected/ghosted/parked/offer."
    ),
    limit: int = typer.Option(50, "--limit", "-n"),
) -> None:
    """One-screen funnel view across all opportunities."""
    from pega_agent.db import list_pipeline, load_job, load_matches
    rows = list_pipeline(stage=stage, exclude_terminal=active_only, limit=limit)
    if not rows:
        console.print("[yellow]No pipeline rows. Run `pega pipeline sync` first.[/yellow]")
        return
    # build score lookup + sort rows by score desc (highest-leverage first)
    scores = {m.job_id: m.score for m in load_matches(limit=500)}
    rows = sorted(rows, key=lambda r: scores.get(r.job_id, 0), reverse=True)
    t = Table(title=f"Pipeline ({len(rows)} opportunities)")
    t.add_column("job", overflow="fold")
    t.add_column("company")
    t.add_column("score", justify="right")
    t.add_column("stage")
    t.add_column("next action")
    t.add_column("updated")
    for r in rows:
        j = load_job(r.job_id)
        color = _STAGE_COLORS.get(r.stage, "white")
        t.add_row(
            (j.title if j else r.job_id)[:55],
            (j.company if j else "—")[:25],
            f"{scores.get(r.job_id, 0):.2f}",
            f"[{color}]{r.stage}[/{color}]",
            r.next_action_at.strftime("%m-%d") if r.next_action_at else "—",
            r.updated_at.strftime("%m-%d"),
        )
    console.print(t)


@pipeline_app.command("show")
def pipeline_show(job_id: str = typer.Argument(...)) -> None:
    """Full detail for one opportunity: job, brief, intros, outreach, notes."""
    from pega_agent.db import (
        OutreachLogRow,
        get_engine,
        get_pipeline,
        load_brief,
        load_job,
        load_recruiter_intros_for_job,
    )
    from sqlalchemy.orm import Session as _S

    job = load_job(job_id)
    if not job:
        console.print(f"[red]Job not found:[/red] {job_id}")
        raise typer.Exit(1)
    p = get_pipeline(job_id)
    console.rule(f"[bold]{job.title} @ {job.company}[/bold]")
    console.print(f"[dim]{job.url}[/dim]")
    if p:
        color = _STAGE_COLORS.get(p.stage, "white")
        console.print(f"Stage: [{color}]{p.stage}[/{color}]")
        if p.next_action_at:
            console.print(f"Next action: {p.next_action_at.strftime('%Y-%m-%d')}")
        if p.notes:
            console.print(f"[bold]Notes:[/bold]\n{p.notes}")
    else:
        console.print("[yellow]No pipeline row (run `pega pipeline sync`).[/yellow]")
    brief = load_brief(job.company)
    if brief:
        console.print(f"\n[bold]Brief:[/bold] {brief.what_they_do[:200]}…")
    intros = load_recruiter_intros_for_job(job_id)
    if intros:
        console.print(f"\n[bold]Recruiter intros drafted:[/bold] {len(intros)}")
        for i in intros:
            console.print(f"  • {i.firm} ({i.generated_at.strftime('%m-%d')})")
    engine = get_engine()
    with _S(engine) as s:
        outs = s.query(OutreachLogRow).filter(OutreachLogRow.job_id == job_id).all()
    if outs:
        console.print(f"\n[bold]Outreach events:[/bold] {len(outs)}")
        for o in outs:
            console.print(
                f"  • {o.updated_at.strftime('%m-%d')} → {o.contact_name} ({o.firm or '—'}): [yellow]{o.status}[/yellow]"
            )


@pipeline_app.command("set")
def pipeline_set(
    job_id: str = typer.Argument(...),
    stage: str = typer.Argument(..., help="One of: " + ", ".join([
        "discovered", "researching", "tailored", "outreach_sent",
        "reply_received", "applied", "screen_scheduled", "onsite",
        "offer", "rejected", "ghosted", "parked",
    ])),
    note: str = typer.Option(None, "--note", "-m"),
    days_to_next: int = typer.Option(None, "--in", help="Set next_action_at = today + N days."),
    force: bool = typer.Option(False, "--force", help="Allow downgrading stage."),
) -> None:
    """Manually advance/rewind the pipeline stage for a job."""
    from pega_agent.db import PIPELINE_STAGES, upsert_pipeline
    if stage not in PIPELINE_STAGES:
        console.print(f"[red]Unknown stage:[/red] {stage}")
        raise typer.Exit(1)
    from datetime import timedelta
    next_at = (datetime.utcnow() + timedelta(days=days_to_next)) if days_to_next else None
    p = upsert_pipeline(job_id, stage=stage, next_action_at=next_at, note=note, force_stage=force)
    color = _STAGE_COLORS.get(p.stage, "white")
    console.print(f"[green]Updated[/green] {job_id} → [{color}]{p.stage}[/{color}]")


@pipeline_app.command("due")
def pipeline_due(within_days: int = typer.Option(0, "--within-days", "-d")) -> None:
    """Show opportunities whose next_action_at is on/before today (+within_days)."""
    from datetime import timedelta
    from pega_agent.db import list_pipeline, load_job
    cutoff = datetime.utcnow() + timedelta(days=within_days)
    rows = [
        r for r in list_pipeline(exclude_terminal=True, limit=500)
        if r.next_action_at and r.next_action_at <= cutoff
    ]
    if not rows:
        console.print("[green]Nothing due.[/green]")
        return
    t = Table(title=f"Due actions ({len(rows)})")
    t.add_column("due")
    t.add_column("job")
    t.add_column("company")
    t.add_column("stage")
    for r in sorted(rows, key=lambda x: x.next_action_at):  # type: ignore[arg-type]
        j = load_job(r.job_id)
        color = _STAGE_COLORS.get(r.stage, "white")
        t.add_row(
            r.next_action_at.strftime("%m-%d"),  # type: ignore[union-attr]
            (j.title if j else r.job_id)[:50],
            (j.company if j else "—")[:25],
            f"[{color}]{r.stage}[/{color}]",
        )
    console.print(t)


@app.command("apply")
def apply_cmd(
    job_id: str = typer.Argument(...),
    url: str = typer.Option(None, "--url", "-u", help="ATS submission URL (optional)."),
    note: str = typer.Option(None, "--note", "-m"),
    follow_up_days: int = typer.Option(
        7, "--follow-up-days", help="Schedule next_action_at in N days (0 to disable)."
    ),
) -> None:
    """Record that you submitted an application via the company ATS."""
    from datetime import timedelta
    from pega_agent.db import upsert_pipeline
    full_note = note or ""
    if url:
        full_note = (f"applied via {url}" + (f" — {note}" if note else "")).strip()
    next_at = (datetime.utcnow() + timedelta(days=follow_up_days)) if follow_up_days else None
    p = upsert_pipeline(job_id, stage="applied", next_action_at=next_at, note=full_note)
    color = _STAGE_COLORS.get(p.stage, "white")
    console.print(
        f"[green]Recorded application[/green] for {job_id} → [{color}]{p.stage}[/{color}]"
        + (f"  (follow up by {next_at.strftime('%Y-%m-%d')})" if next_at else "")
    )


if __name__ == "__main__":
    app()
