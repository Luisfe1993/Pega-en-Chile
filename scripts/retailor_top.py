"""Re-tailor the top N already-loaded jobs using the current profile.yaml.
Useful after updating the profile to flow new content through cached CVs.
"""

from pathlib import Path

import typer

from pega_agent.db import get_engine, load_brief, load_job, save_cover_letter
from pega_agent.profile.agent import load_profile
from pega_agent.tailor.agent import draft_cover_letter, tailor_cv
from sqlalchemy import text

app = typer.Typer()


@app.command()
def main(n: int = 3, profile_path: Path = Path("data/profile.yaml")) -> None:
    profile = load_profile(profile_path)
    eng = get_engine()
    with eng.connect() as c:
        rows = c.execute(
            text(
                "SELECT m.job_id FROM matches m "
                "ORDER BY m.score DESC LIMIT :n"
            ),
            {"n": n},
        ).fetchall()
    job_ids = [r[0] for r in rows]
    print(f"Re-tailoring {len(job_ids)} jobs with refreshed profile…")
    for jid in job_ids:
        job = load_job(jid)
        if not job:
            print(f"  skip {jid}: not in DB")
            continue
        brief = load_brief(job.company)
        cv = tailor_cv(profile, job, brief)
        cl = draft_cover_letter(profile, job, cv, brief)
        save_cover_letter(cl)
        print(
            f"  ✓ {job.company} · {job.title} | "
            f"lang={cv.language} | bullets={len(cv.bullets)} | "
            f"cover_lang={cl.language}"
        )


if __name__ == "__main__":
    app()
