"""LinkedIn contacts agent.

Reads a LinkedIn data export (Connections/Invitations/messages/Company Follows/
Endorsements), normalizes companies for prospect matching, and verifies emails
using free signals only (syntax + MX). NO Apollo/Hunter/paid APIs.

Tiering for outreach plan:
    A = 1st-degree connection + verified email (mx_ok)
    B = 1st-degree connection, no usable email
    C = followed-company prospect (warm intent signal)
    D = needs cold outreach (no warm path found)
"""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Iterable

from rich.console import Console

from pega_agent import db

console = Console()


# ----------------------------------------------------------------------------
# Company normalization
# ----------------------------------------------------------------------------

_COMPANY_SUFFIXES = [
    r"\bs\.\s*a\.\s*c\.\s*i\.\b",
    r"\bs\.\s*a\.\s*c\.\b",
    r"\bs\.\s*a\.\b",
    r"\bs\.\s*p\.\s*a\.\b",
    r"\bspa\b",
    r"\bltda\.?\b",
    r"\bltd\.?\b",
    r"\binc\.?\b",
    r"\bcorp\.?\b",
    r"\bcorporation\b",
    r"\bcompany\b",
    r"\bco\.\b",
    r"\bllc\b",
    r"\bgmbh\b",
    r"\bplc\b",
    r"\bgroup\b",
    r"\bholding[s]?\b",
    r"\bag\b",
    r"\bn\.\s*v\.\b",
    r"\bb\.\s*v\.\b",
    r"\.com\b",
    r"\bchile\b",
    r"\bsudamerica\b",
    r"\bsudamericana\b",
    r"\blatam\b",
    r"\blatinoamerica\b",
    r"\binternational\b",
]


def normalize_company(name: str | None) -> str:
    if not name:
        return ""
    s = name.lower().strip().replace("&", "and")
    # Only strip a suffix if the remainder is still meaningful
    # (≥3 chars with at least one letter). Prevents "Group-IB" → "ib".
    for pat in _COMPANY_SUFFIXES:
        candidate = re.sub(pat, " ", s)
        cleaned = re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", candidate)).strip()
        if len(cleaned) >= 3 and any(ch.isalpha() for ch in cleaned):
            s = candidate
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


# ----------------------------------------------------------------------------
# Date parsers
# ----------------------------------------------------------------------------

def _parse_connection_date(s: str) -> datetime | None:
    s = (s or "").strip()
    if not s:
        return None
    # "26 May 2026"
    for fmt in ("%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _parse_invitation_date(s: str) -> datetime | None:
    s = (s or "").strip()
    if not s:
        return None
    # "6/1/26, 7:19 AM"
    for fmt in ("%m/%d/%y, %I:%M %p", "%m/%d/%Y, %I:%M %p"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _parse_message_date(s: str) -> datetime | None:
    s = (s or "").strip()
    if not s:
        return None
    # "2026-06-06 18:33:31 UTC"
    s2 = s.replace(" UTC", "")
    try:
        return datetime.strptime(s2, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _parse_follow_date(s: str) -> datetime | None:
    s = (s or "").strip()
    if not s:
        return None
    # "Wed Jun 03 18:44:33 UTC 2026"
    try:
        return datetime.strptime(s, "%a %b %d %H:%M:%S UTC %Y")
    except ValueError:
        return None


# ----------------------------------------------------------------------------
# CSV reading (handles LinkedIn's "Notes:" preamble in Connections.csv)
# ----------------------------------------------------------------------------

def _open_linkedin_csv(path: Path, header_starts_with: str) -> Iterable[dict]:
    """Yield dicts from a LinkedIn CSV, skipping any preamble before the header."""
    if not path.exists():
        return
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        lines = f.readlines()
    header_idx = None
    for i, line in enumerate(lines):
        stripped = line.lstrip().lstrip('"').lstrip("'")
        if stripped.startswith(header_starts_with):
            header_idx = i
            break
    if header_idx is None:
        return
    body = lines[header_idx:]
    reader = csv.DictReader(body)
    for row in reader:
        yield row


# ----------------------------------------------------------------------------
# Importers
# ----------------------------------------------------------------------------

def import_connections(path: Path) -> int:
    rows: list[dict] = []
    for r in _open_linkedin_csv(path, "First Name"):
        url = (r.get("URL") or "").strip()
        first = (r.get("First Name") or "").strip()
        last = (r.get("Last Name") or "").strip()
        if not url and not first and not last:
            continue  # blank row
        if not url:
            # synthesize key from name (low-quality, but keep the record)
            slug = re.sub(r"\s+", "-", f"{first}-{last}".lower()).strip("-")
            url = f"missing-url://{slug}"
        company = (r.get("Company") or "").strip() or None
        rows.append({
            "linkedin_url": url,
            "full_name": f"{first} {last}".strip(),
            "first_name": first or None,
            "last_name": last or None,
            "company": company,
            "company_norm": normalize_company(company) or None,
            "position": (r.get("Position") or "").strip() or None,
            "connected_on": _parse_connection_date(r.get("Connected On", "")),
            "email": (r.get("Email Address") or "").strip().lower() or None,
            "email_source": "linkedin_export" if (r.get("Email Address") or "").strip() else "none",
        })
    return db.bulk_upsert_contacts(rows)


def import_invitations(path: Path) -> int:
    """Mark invitation direction on existing/new contacts."""
    n = 0
    for r in _open_linkedin_csv(path, "From"):
        direction = (r.get("Direction") or "").strip().upper()
        if direction == "OUTGOING":
            url = (r.get("inviteeProfileUrl") or "").strip()
            name = (r.get("To") or "").strip()
        elif direction == "INCOMING":
            url = (r.get("inviterProfileUrl") or "").strip()
            name = (r.get("From") or "").strip()
        else:
            continue
        if not url:
            continue
        # upsert minimal contact + direction
        db.upsert_contact({
            "linkedin_url": url,
            "full_name": name or "(unknown)",
            "invitation_direction": direction.lower(),
        })
        n += 1
    return n


def import_messages(path: Path) -> int:
    """Aggregate message recency + counts per contact URL."""
    own_signals = {"luis", "sande", "luisfelipesande"}
    counts: dict[str, dict] = defaultdict(lambda: {"count": 0, "last": None, "direction": None})
    for r in _open_linkedin_csv(path, "CONVERSATION ID"):
        sender_url = (r.get("SENDER PROFILE URL") or "").strip()
        recip_urls = (r.get("RECIPIENT PROFILE URLS") or "").strip()
        from_name = (r.get("FROM") or "").strip().lower()
        date = _parse_message_date(r.get("DATE", ""))
        if not date:
            continue
        is_self_sender = any(tok in sender_url.lower() or tok in from_name for tok in own_signals)
        # Identify the OTHER party in the conversation
        other_urls: list[str] = []
        if is_self_sender:
            # outgoing — others are recipients
            for u in recip_urls.split(";"):
                u = u.strip()
                if u and not any(tok in u.lower() for tok in own_signals):
                    other_urls.append(u)
            direction = "outgoing"
        else:
            if sender_url and not any(tok in sender_url.lower() for tok in own_signals):
                other_urls.append(sender_url)
            direction = "incoming"
        for u in other_urls:
            entry = counts[u]
            entry["count"] += 1
            if entry["last"] is None or date > entry["last"]:
                entry["last"] = date
                entry["direction"] = direction
    n = 0
    for url, info in counts.items():
        ok = db.update_contact_messaging(
            url, info["last"], info["direction"], msg_count_delta=info["count"]
        )
        if not ok:
            # contact not in DB yet (we never connected) — create a stub
            db.upsert_contact({
                "linkedin_url": url,
                "full_name": "(via messages)",
                "last_message_at": info["last"],
                "last_message_direction": info["direction"],
                "msg_count": info["count"],
            })
        n += 1
    return n


def import_company_follows(path: Path) -> int:
    n = 0
    for r in _open_linkedin_csv(path, "Organization"):
        org = (r.get("Organization") or "").strip()
        if not org:
            continue
        db.upsert_company_follow(
            organization=org,
            organization_norm=normalize_company(org),
            followed_on=_parse_follow_date(r.get("Followed On", "")),
        )
        n += 1
    return n


def import_endorsements(path: Path) -> int:
    """Count endorsements RECEIVED grouped by endorser profile URL."""
    if not path.exists():
        return 0
    # Inspect header to find URL col
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        url_col = None
        for cand in ("Endorser Public Url", "Endorser Profile URL", "Endorser Url"):
            if reader.fieldnames and cand in reader.fieldnames:
                url_col = cand
                break
        if not url_col:
            return 0
        counts: dict[str, int] = defaultdict(int)
        for row in reader:
            u = (row.get(url_col) or "").strip()
            if u:
                counts[u] += 1
    n = 0
    for url, c in counts.items():
        if db.update_contact_endorsement(url, c):
            n += 1
    return n


def import_linkedin_export(directory: Path) -> dict[str, int]:
    """Import all known LinkedIn CSVs from a directory."""
    result = {
        "connections": import_connections(directory / "Connections.csv"),
        "invitations": import_invitations(directory / "Invitations.csv"),
        "messages": import_messages(directory / "messages.csv"),
        "company_follows": import_company_follows(directory / "Company Follows.csv"),
        "endorsements": import_endorsements(directory / "Endorsement_Received_Info.csv"),
    }
    return result


# ----------------------------------------------------------------------------
# Email verification (free stack: syntax + MX)
# ----------------------------------------------------------------------------

def verify_email_free(addr: str) -> tuple[str, str]:
    """Return (status, detail). status in: invalid | mx_ok."""
    try:
        from email_validator import EmailNotValidError, validate_email
    except ImportError:
        return "unverified", "email-validator not installed"
    try:
        v = validate_email(addr, check_deliverability=False)
    except EmailNotValidError as e:
        return "invalid", str(e)
    domain = v.domain
    try:
        import dns.resolver
    except ImportError:
        return "unverified", "dnspython not installed"
    try:
        answers = dns.resolver.resolve(domain, "MX", lifetime=5)
        if not list(answers):
            return "invalid", "no MX records"
    except Exception as e:
        return "invalid", f"MX lookup failed: {e}"
    return "mx_ok", v.normalized


def verify_all_contact_emails() -> dict[str, int]:
    """Verify every contact with an email; updates DB. Returns counts by status."""
    counts: dict[str, int] = defaultdict(int)
    for c in db.list_contacts_with_email():
        if c.email_status in ("mx_ok", "smtp_ok"):
            counts["already_verified"] += 1
            continue
        status, detail = verify_email_free(c.email)
        db.update_contact_email_status(c.linkedin_url, status, detail[:80])
        counts[status] += 1
    return dict(counts)


# ----------------------------------------------------------------------------
# Matching + tiering + report
# ----------------------------------------------------------------------------

_SENIORITY = [
    (3, ("chief", "cto", "cfo", "ceo", "cpo", "cco", "cmo", "founder", "co-founder")),
    (3, ("vp ", "vice president", "vicepresid", "vicepresident")),
    (2, ("director", "head of", "head, ", "gerente general", "country manager", "general manager")),
    (2, ("gerente", "manager")),
    (1, ("lead", "principal", "staff")),
    (1, ("senior", "sr.", "sr ")),
]


def _seniority_score(position: str | None) -> int:
    if not position:
        return 0
    p = position.lower()
    for score, keys in _SENIORITY:
        if any(k in p for k in keys):
            return score
    return 0


def _tier(contact, is_followed_company: bool) -> str:
    is_real_contact = not contact.linkedin_url.startswith("missing-url://")
    has_verified_email = contact.email_status in ("mx_ok", "smtp_ok") and bool(contact.email)
    if is_real_contact and has_verified_email:
        return "A"
    if is_real_contact:
        return "B"
    if is_followed_company:
        return "C"
    return "D"


def match_contacts_to_prospects(
    prospect_companies: list[str],
) -> dict[str, list]:
    """For each prospect company, return matched ContactRow objects sorted by usefulness."""
    out: dict[str, list] = {}
    for raw in prospect_companies:
        norm = normalize_company(raw)
        if not norm:
            continue
        matches = db.list_contacts_by_company_norm(norm)
        # rank: seniority desc, then msg recency desc, then connection recency desc
        matches.sort(
            key=lambda c: (
                _seniority_score(c.position),
                c.last_message_at or datetime.min,
                c.connected_on or datetime.min,
            ),
            reverse=True,
        )
        out[raw] = matches
    return out


def render_outreach_plan(
    matches: dict[str, list],
    top_n_per_company: int = 5,
) -> str:
    follows_norm = {f.organization_norm for f in db.list_company_follows()}
    lines: list[str] = []
    lines.append("# Outreach Plan — Warm Paths Discovered\n")
    lines.append(
        f"_Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}._\n"
    )
    lines.append(
        "Tiers: **A** verified-email connection, **B** 1st-degree (LinkedIn DM), "
        "**C** prospect already followed (warm intent), **D** cold.\n\n"
    )

    total_a = total_b = total_c_only = 0
    for company, contacts in matches.items():
        norm = normalize_company(company)
        is_followed = any(
            norm and (norm in fn or fn in norm) for fn in follows_norm if fn
        )
        followed_marker = " :star: *(already followed)*" if is_followed else ""
        lines.append(f"## {company}{followed_marker}\n")
        if not contacts:
            tier = "C" if is_followed else "D"
            lines.append(f"_No 1st-degree contacts — Tier {tier}_\n\n")
            if is_followed:
                total_c_only += 1
            continue
        for c in contacts[:top_n_per_company]:
            t = _tier(c, is_followed)
            if t == "A":
                total_a += 1
            elif t == "B":
                total_b += 1
            bits = [f"**[{t}]** {c.full_name}"]
            if c.position:
                bits.append(f"_{c.position}_")
            if c.email:
                status_emoji = "✅" if c.email_status == "mx_ok" else "⚠️"
                bits.append(f"`{c.email}` {status_emoji}{c.email_status}")
            if c.last_message_at:
                dir_marker = "→" if c.last_message_direction == "outgoing" else "←"
                bits.append(
                    f"last msg {dir_marker} {c.last_message_at.strftime('%Y-%m-%d')}"
                )
            if c.connected_on:
                bits.append(f"connected {c.connected_on.strftime('%Y-%m')}")
            if not c.linkedin_url.startswith("missing-url://"):
                bits.append(f"[LinkedIn]({c.linkedin_url})")
            lines.append("- " + " • ".join(bits))
        lines.append("")

    summary = (
        f"\n---\n\n**Summary:** {total_a} Tier-A (email-verified) · "
        f"{total_b} Tier-B (LinkedIn DM) · "
        f"{total_c_only} Tier-C (followed-company, cold)\n"
    )
    lines.append(summary)
    return "\n".join(lines)


# ----------------------------------------------------------------------------
# LinkedIn DM drafter (short, casual; no salutation, no signature)
# ----------------------------------------------------------------------------

_DM_PROMPT_STR = (
    "system",
    (
        "You draft a SHORT LinkedIn direct message from a senior product leader\n"
        "to a 1st-degree connection about a SPECIFIC opening at their company.\n"
        "Produce BOTH Spanish (informal 'tú') AND English versions of the body.\n\n"
        "Hard rules:\n"
        "  - 55-90 words. Paste-ready. Direct.\n"
        "  - FIRST PERSON ('yo'/'I'). Open with 'Hola {first_name},' or 'Hi {first_name},'.\n"
        "  - Sentence 1: warm one-liner. If we've spoken before, reference loosely\n"
        "    ('hace un tiempo / a while back'); otherwise the connection itself.\n"
        "  - Sentence 2-3: the SPECIFIC opening + ONE concrete proof point from\n"
        "    the candidate's bullets that maps to the role.\n"
        "  - Sentence 4: low-pressure ask — 15-min chat OR introduction to the\n"
        "    hiring manager. Do NOT ask for a referral up front.\n"
        "  - NO salutation 'Estimado/a'. NO email signature. NO subject line.\n"
        "  - NO buzzwords ('leverage', 'synergy', 'passionate', 'impact-driven').\n"
        "  - Do NOT fabricate achievements not in the candidate bullets.\n"
        "  - Do NOT invent the contact's title; use what's in the prompt.\n"
    ),
)

_DM_USER_STR = (
    "user",
    (
        "Candidate: {name} ({headline})\n"
        "Candidate bullets (only use these as proof points):\n{bullets}\n\n"
        "Contact first name: {first_name}\n"
        "Contact full name: {contact_name}\n"
        "Contact current title: {contact_title}\n"
        "Connected since: {connected_on}\n"
        "Prior interaction: {prior}\n\n"
        "Opening:\n"
        "  Title: {job_title}\n"
        "  Company: {job_company}\n"
        "  Location: {job_location}\n"
        "  Description excerpt:\n```\n{job_description}\n```\n"
    ),
)


def draft_linkedin_dm(
    profile,
    job,
    contact,
) -> dict[str, str]:
    """Generate a short bilingual LinkedIn DM for a 1st-degree contact.

    Returns dict with body_es, body_en. Does not persist.
    """
    from langchain_core.prompts import ChatPromptTemplate
    from pydantic import BaseModel

    class _DMDraftLocal(BaseModel):
        body_es: str
        body_en: str

    from pega_agent.llm import get_chat_model
    from pega_agent.recruiter.agent import _flatten_bullets

    model = get_chat_model(temperature=0.3)
    prompt = ChatPromptTemplate.from_messages([_DM_PROMPT_STR, _DM_USER_STR])
    chain = prompt | model.with_structured_output(_DMDraftLocal)

    first_name = contact.first_name or (contact.full_name.split(" ")[0] if contact.full_name else "")
    prior_bits: list[str] = []
    if contact.msg_count and contact.msg_count > 0:
        last = (
            contact.last_message_at.strftime("%Y-%m") if contact.last_message_at else "?"
        )
        dirn = contact.last_message_direction or "?"
        prior_bits.append(f"we exchanged messages ({contact.msg_count}); last={last} dir={dirn}")
    if contact.endorsement_count and contact.endorsement_count > 0:
        prior_bits.append(f"endorsed me {contact.endorsement_count}x")
    if not prior_bits:
        prior_bits.append("none beyond LinkedIn connection")

    draft = chain.invoke(
        {
            "name": profile.name,
            "headline": profile.headline or "",
            "bullets": _flatten_bullets(profile),
            "first_name": first_name,
            "contact_name": contact.full_name,
            "contact_title": contact.position or "(unknown)",
            "connected_on": (
                contact.connected_on.strftime("%Y-%m") if contact.connected_on else "?"
            ),
            "prior": "; ".join(prior_bits),
            "job_title": job.title,
            "job_company": job.company,
            "job_location": job.location or "",
            "job_description": (job.description or "")[:2000],
        }
    )
    return {"body_es": draft.body_es, "body_en": draft.body_en}


# ----------------------------------------------------------------------------
# Email guesser (pattern + MX verify)
# ----------------------------------------------------------------------------

def _email_patterns(first: str, last: str, domain: str) -> list[str]:
    import unicodedata as _u
    def fold(s: str) -> str:
        s = _u.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
        return re.sub(r"[^a-z]", "", s.lower())
    f = fold(first)
    l = fold(last)
    d = (domain or "").lower().strip().lstrip("@")
    if not f or not d:
        return []
    pats: list[str] = []
    if l:
        pats.extend([
            f"{f}.{l}@{d}",
            f"{f}{l}@{d}",
            f"{f[0]}{l}@{d}",
            f"{f}.{l[0]}@{d}",
            f"{f}_{l}@{d}",
            f"{l}.{f}@{d}",
        ])
    pats.append(f"{f}@{d}")
    return pats


def guess_and_verify_email(
    contact,
    domain: str,
    save: bool = True,
) -> tuple[str | None, str]:
    """Try common patterns for `domain`, MX-verify each, return first that passes.

    Returns (email_or_None, status_or_reason). If save=True, persists the winner
    on the contact (email_source='guessed', email_status='mx_ok').
    """
    if not contact.first_name and not contact.full_name:
        return None, "no first name"
    first = contact.first_name or contact.full_name.split(" ")[0]
    last = contact.last_name or (
        contact.full_name.split(" ")[-1] if contact.full_name else ""
    )
    for candidate in _email_patterns(first, last, domain):
        status, _ = verify_email_free(candidate)
        if status == "mx_ok":
            if save:
                from pega_agent.db import upsert_contact
                upsert_contact({
                    "linkedin_url": contact.linkedin_url,
                    "full_name": contact.full_name,
                    "email": candidate,
                    "email_source": "guessed",
                    "email_status": "mx_ok",
                    "last_verified_at": datetime.utcnow(),
                })
            return candidate, "mx_ok"
    return None, "no pattern passed MX (domain may be catch-all or unreachable)"
