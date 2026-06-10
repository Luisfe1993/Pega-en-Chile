"""Map this week's digest picks to internal job_ids + contact counts."""
from sqlalchemy.orm import Session

from pega_agent.db import (
    CompanyBriefRow,
    ContactRow,
    CoverLetterRow,
    JobRow,
    TailoredCVRow,
    get_engine,
)

PICKS = [
    ("Genesys",    "f517b41c743a9a44"),
    ("TechBiz",    "3d122c62eabaa493"),
    ("Red Hat",    "3b4e861b660d0021"),
    ("Caterpillar","10ef7552b38b1210"),
    ("Le Creuset", "68a2a3e1ddc3ca31"),
    ("FLSmidth",   "f6269b996c4bfa61"),
    ("Terrific",   "4418988956"),
]

with Session(get_engine()) as s:
    print(f"{'Label':12s} {'JobID':18s} {'Company':22s} br cv cl 1st mx Title")
    print("-" * 130)
    for label, frag in PICKS:
        row = s.query(JobRow).filter(JobRow.url.like(f"%{frag}%")).first()
        if not row:
            print(f"{label:12s}  NOT FOUND  '{frag}'")
            continue
        comp = (row.company or "").strip()
        token = comp.split()[0].lower() if comp else ""
        contacts: list[ContactRow] = []
        if token and len(token) >= 4:
            contacts = (
                s.query(ContactRow)
                .filter(ContactRow.company_norm.like(f"%{token}%"))
                .all()
            )
        verified = [c for c in contacts if (c.email_status or "") == "mx_ok"]
        has_brief = bool(s.get(CompanyBriefRow, comp))
        has_cv = bool(s.get(TailoredCVRow, row.id))
        has_cl = bool(s.get(CoverLetterRow, row.id))
        b = "OK" if has_brief else "--"
        c_ = "OK" if has_cv else "--"
        l = "OK" if has_cl else "--"
        print(
            f"{label:12s} {row.id:18s} {comp[:22]:22s} {b:2s} {c_:2s} {l:2s} "
            f"{len(contacts):>3d} {len(verified):>2d} {row.title[:50]}"
        )
        for c in verified[:3]:
            ttl = (c.position or "")[:35]
            nm = (c.full_name or "")[:30]
            print(f"             └─ {nm:30s}  {ttl:35s}  {c.email or ''}")
