"""For each pick, surface: 1st-degree warm contacts + recruiter-firm coverage."""
from pathlib import Path

from sqlalchemy.orm import Session

from pega_agent.db import ContactRow, JobRow, get_engine
from pega_agent.recruiter import load_recruiters_yaml

PICKS = [
    ("Genesys",    "ab3f5baea19d6cb0"),
    ("TechBiz",    "225499c6cf8952fd"),
    ("Red Hat",    "b859d09f7da605be"),
    ("Caterpillar","44d534794bcf01d6"),
    ("Le Creuset", "852a58cf705514a6"),
    ("FLSmidth",   "f63932ceefc454a1"),
    ("Terrific",   "4f81ee928becd03f"),
]

cfg = load_recruiters_yaml(Path("data/recruiters.yaml"))
firms = [f.get("name", "") for f in cfg.get("target_firms", [])]
warm = cfg.get("warm_contacts", [])

with Session(get_engine()) as s:
    for label, jid in PICKS:
        job = s.get(JobRow, jid)
        if not job:
            continue
        comp = (job.company or "").strip()
        token = comp.split()[0].lower() if comp else ""

        # 1st-degree contacts at the company
        contacts: list[ContactRow] = []
        if token and len(token) >= 4:
            contacts = (
                s.query(ContactRow)
                .filter(ContactRow.company_norm.like(f"%{token}%"))
                .all()
            )

        # Strict match: contact's normalized company starts with or equals our token
        strict = [c for c in contacts if (c.company_norm or "").startswith(token) or token in (c.company_norm or "").split()]

        # warm recruiter contact whose firm covers this company?
        warm_for = [w for w in warm if comp.lower() in (str(w.get("notes") or "") + " " + str(w.get("firm") or "")).lower()]

        print(f"\n=== {label}  ({comp})  →  {jid} ===")
        if strict:
            print(f"  1st-degree at {comp}:")
            for c in strict[:5]:
                line = f"    - {c.full_name}"
                if c.position: line += f"  |  {c.position[:50]}"
                if c.email: line += f"  |  {c.email} ({c.email_status})"
                if c.linkedin_url: line += f"\n        {c.linkedin_url}"
                print(line)
        else:
            print("  1st-degree at company: NONE")

        if warm_for:
            print("  warm recruiter:")
            for w in warm_for:
                print(f"    - {w.get('name')} @ {w.get('firm')}")
        else:
            print(f"  recruiter firms to consider: {', '.join(firms[:3])}")
