from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from pega_agent.config import settings
from pega_agent.models import (
    ApprovalDecision,
    CompanyBrief,
    CoverLetter,
    InterviewPrepPack,
    JobPosting,
    MatchScore,
    NegotiationDraft,
    OutreachDraft,
    OutreachLogEntry,
    RecruiterIntro,
    TailoredCV,
)


class Base(DeclarativeBase):
    pass


class JobRow(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    source: Mapped[str] = mapped_column(String, index=True)
    url: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String)
    company: Mapped[str] = mapped_column(String, index=True)
    location: Mapped[str | None] = mapped_column(String, nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON)
    discovered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MatchRow(Base):
    __tablename__ = "matches"
    job_id: Mapped[str] = mapped_column(String, primary_key=True)
    score: Mapped[float] = mapped_column(Float, index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    scored_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CompanyBriefRow(Base):
    __tablename__ = "company_briefs"
    company: Mapped[str] = mapped_column(String, primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TailoredCVRow(Base):
    __tablename__ = "tailored_cvs"
    job_id: Mapped[str] = mapped_column(String, primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CoverLetterRow(Base):
    __tablename__ = "cover_letters"
    job_id: Mapped[str] = mapped_column(String, primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class OutreachRow(Base):
    __tablename__ = "outreach"
    job_id: Mapped[str] = mapped_column(String, primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ApprovalRow(Base):
    __tablename__ = "approvals"
    id: Mapped[str] = mapped_column(String, primary_key=True)  # f"{job_id}|{artifact}"
    job_id: Mapped[str] = mapped_column(String, index=True)
    artifact: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    decided_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class InterviewPrepRow(Base):
    __tablename__ = "interview_prep"
    job_id: Mapped[str] = mapped_column(String, primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class NegotiationRow(Base):
    __tablename__ = "negotiations"
    job_id: Mapped[str] = mapped_column(String, primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class RecruiterIntroRow(Base):
    __tablename__ = "recruiter_intros"
    # composite key job_id|firm allows multiple firms per job
    id: Mapped[str] = mapped_column(String, primary_key=True)
    job_id: Mapped[str] = mapped_column(String, index=True)
    firm: Mapped[str] = mapped_column(String, index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class OutreachLogRow(Base):
    __tablename__ = "outreach_log"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    contact_name: Mapped[str] = mapped_column(String, index=True)
    firm: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    job_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    status: Mapped[str] = mapped_column(String, index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ContactRow(Base):
    __tablename__ = "contacts"
    linkedin_url: Mapped[str] = mapped_column(String, primary_key=True)
    full_name: Mapped[str] = mapped_column(String, index=True)
    first_name: Mapped[str | None] = mapped_column(String, nullable=True)
    last_name: Mapped[str | None] = mapped_column(String, nullable=True)
    company: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    company_norm: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    position: Mapped[str | None] = mapped_column(String, nullable=True)
    connected_on: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    email_source: Mapped[str] = mapped_column(String, default="none")
    email_status: Mapped[str] = mapped_column(String, default="unverified", index=True)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_message_direction: Mapped[str | None] = mapped_column(String, nullable=True)
    msg_count: Mapped[int] = mapped_column(Integer, default=0)
    invitation_direction: Mapped[str | None] = mapped_column(String, nullable=True)
    endorsement_count: Mapped[int] = mapped_column(Integer, default=0)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notes: Mapped[str | None] = mapped_column(String, nullable=True)


class CompanyFollowRow(Base):
    __tablename__ = "company_follows"
    organization: Mapped[str] = mapped_column(String, primary_key=True)
    organization_norm: Mapped[str] = mapped_column(String, index=True)
    followed_on: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


def get_engine():
    settings.pega_db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{settings.pega_db_path}", future=True)
    Base.metadata.create_all(engine)
    return engine


def save_jobs(jobs: list[JobPosting]) -> int:
    engine = get_engine()
    inserted = 0
    with Session(engine) as s:
        for j in jobs:
            existing = s.get(JobRow, j.id)
            if existing:
                continue
            s.add(
                JobRow(
                    id=j.id,
                    source=j.source,
                    url=j.url,
                    title=j.title,
                    company=j.company,
                    location=j.location,
                    posted_at=j.posted_at,
                    payload=json.loads(j.model_dump_json()),
                )
            )
            inserted += 1
        s.commit()
    return inserted


def load_jobs(limit: int = 200) -> list[JobPosting]:
    engine = get_engine()
    with Session(engine) as s:
        rows = (
            s.query(JobRow)
            .order_by(JobRow.discovered_at.desc())
            .limit(limit)
            .all()
        )
        return [JobPosting(**r.payload) for r in rows]


def save_matches(scores: list[MatchScore]) -> int:
    engine = get_engine()
    with Session(engine) as s:
        for sc in scores:
            s.merge(
                MatchRow(
                    job_id=sc.job_id,
                    score=sc.score,
                    payload=json.loads(sc.model_dump_json()),
                )
            )
        s.commit()
    return len(scores)


def load_matches(limit: int = 50) -> list[MatchScore]:
    engine = get_engine()
    with Session(engine) as s:
        rows = (
            s.query(MatchRow).order_by(MatchRow.score.desc()).limit(limit).all()
        )
        return [MatchScore(**r.payload) for r in rows]


def save_brief(brief: CompanyBrief) -> None:
    engine = get_engine()
    with Session(engine) as s:
        s.merge(
            CompanyBriefRow(
                company=brief.company.lower(),
                payload=json.loads(brief.model_dump_json()),
                generated_at=brief.generated_at,
            )
        )
        s.commit()


def load_brief(company: str) -> CompanyBrief | None:
    engine = get_engine()
    with Session(engine) as s:
        row = s.get(CompanyBriefRow, company.lower())
        return CompanyBrief(**row.payload) if row else None


def load_briefs(limit: int = 50) -> list[CompanyBrief]:
    engine = get_engine()
    with Session(engine) as s:
        rows = (
            s.query(CompanyBriefRow)
            .order_by(CompanyBriefRow.generated_at.desc())
            .limit(limit)
            .all()
        )
        return [CompanyBrief(**r.payload) for r in rows]


# ---------- Tailor / CoverLetter / Outreach / Approval -------------------


def save_tailored_cv(cv: TailoredCV) -> None:
    engine = get_engine()
    with Session(engine) as s:
        s.merge(
            TailoredCVRow(
                job_id=cv.job_id,
                payload=json.loads(cv.model_dump_json()),
                generated_at=cv.generated_at,
            )
        )
        s.commit()


def load_tailored_cv(job_id: str) -> TailoredCV | None:
    engine = get_engine()
    with Session(engine) as s:
        row = s.get(TailoredCVRow, job_id)
        return TailoredCV(**row.payload) if row else None


def save_cover_letter(cl: CoverLetter) -> None:
    engine = get_engine()
    with Session(engine) as s:
        s.merge(
            CoverLetterRow(
                job_id=cl.job_id,
                payload=json.loads(cl.model_dump_json()),
                generated_at=cl.generated_at,
            )
        )
        s.commit()


def load_cover_letter(job_id: str) -> CoverLetter | None:
    engine = get_engine()
    with Session(engine) as s:
        row = s.get(CoverLetterRow, job_id)
        return CoverLetter(**row.payload) if row else None


def save_outreach(draft: OutreachDraft) -> None:
    engine = get_engine()
    with Session(engine) as s:
        s.merge(
            OutreachRow(
                job_id=draft.job_id,
                payload=json.loads(draft.model_dump_json()),
                generated_at=draft.generated_at,
            )
        )
        s.commit()


def load_outreach(job_id: str) -> OutreachDraft | None:
    engine = get_engine()
    with Session(engine) as s:
        row = s.get(OutreachRow, job_id)
        return OutreachDraft(**row.payload) if row else None


def save_approval(decision: ApprovalDecision) -> None:
    engine = get_engine()
    with Session(engine) as s:
        s.merge(
            ApprovalRow(
                id=f"{decision.job_id}|{decision.artifact}",
                job_id=decision.job_id,
                artifact=decision.artifact,
                status=decision.status,
                payload=json.loads(decision.model_dump_json()),
                decided_at=decision.decided_at,
            )
        )
        s.commit()


def load_approvals(
    job_id: str | None = None, status: str | None = None, limit: int = 200
) -> list[ApprovalDecision]:
    engine = get_engine()
    with Session(engine) as s:
        q = s.query(ApprovalRow)
        if job_id:
            q = q.filter(ApprovalRow.job_id == job_id)
        if status:
            q = q.filter(ApprovalRow.status == status)
        rows = q.order_by(ApprovalRow.decided_at.desc()).limit(limit).all()
        return [ApprovalDecision(**r.payload) for r in rows]


# ---------- Interview Prep / Negotiation ---------------------------------


def save_interview_prep(pack: InterviewPrepPack) -> None:
    engine = get_engine()
    with Session(engine) as s:
        s.merge(
            InterviewPrepRow(
                job_id=pack.job_id,
                payload=json.loads(pack.model_dump_json()),
                generated_at=pack.generated_at,
            )
        )
        s.commit()


def load_interview_prep(job_id: str) -> InterviewPrepPack | None:
    engine = get_engine()
    with Session(engine) as s:
        row = s.get(InterviewPrepRow, job_id)
        return InterviewPrepPack(**row.payload) if row else None


def load_all_prep(limit: int = 50) -> list[InterviewPrepPack]:
    engine = get_engine()
    with Session(engine) as s:
        rows = (
            s.query(InterviewPrepRow)
            .order_by(InterviewPrepRow.generated_at.desc())
            .limit(limit)
            .all()
        )
        return [InterviewPrepPack(**r.payload) for r in rows]


def save_negotiation(neg: NegotiationDraft) -> None:
    engine = get_engine()
    with Session(engine) as s:
        s.merge(
            NegotiationRow(
                job_id=neg.job_id,
                payload=json.loads(neg.model_dump_json()),
                generated_at=neg.generated_at,
            )
        )
        s.commit()


def load_negotiation(job_id: str) -> NegotiationDraft | None:
    engine = get_engine()
    with Session(engine) as s:
        row = s.get(NegotiationRow, job_id)
        return NegotiationDraft(**row.payload) if row else None


def load_all_negotiations(limit: int = 50) -> list[NegotiationDraft]:
    engine = get_engine()
    with Session(engine) as s:
        rows = (
            s.query(NegotiationRow)
            .order_by(NegotiationRow.generated_at.desc())
            .limit(limit)
            .all()
        )
        return [NegotiationDraft(**r.payload) for r in rows]


def load_job(job_id: str) -> JobPosting | None:
    """Get a single job by id; used by post-approval agents."""
    engine = get_engine()
    with Session(engine) as s:
        row = s.get(JobRow, job_id)
        return JobPosting(**row.payload) if row else None


# ---------- Recruiter intros + Outreach log ------------------------------


def _recruiter_intro_key(job_id: str, firm: str) -> str:
    return f"{job_id}|{firm.lower()}"


def save_recruiter_intro(intro: RecruiterIntro) -> None:
    engine = get_engine()
    with Session(engine) as s:
        s.merge(
            RecruiterIntroRow(
                id=_recruiter_intro_key(intro.job_id, intro.firm),
                job_id=intro.job_id,
                firm=intro.firm,
                payload=json.loads(intro.model_dump_json()),
                generated_at=intro.generated_at,
            )
        )
        s.commit()


def load_recruiter_intro(job_id: str, firm: str) -> RecruiterIntro | None:
    engine = get_engine()
    with Session(engine) as s:
        row = s.get(RecruiterIntroRow, _recruiter_intro_key(job_id, firm))
        return RecruiterIntro(**row.payload) if row else None


def load_recruiter_intros_for_job(job_id: str) -> list[RecruiterIntro]:
    engine = get_engine()
    with Session(engine) as s:
        rows = (
            s.query(RecruiterIntroRow)
            .filter(RecruiterIntroRow.job_id == job_id)
            .order_by(RecruiterIntroRow.generated_at.desc())
            .all()
        )
        return [RecruiterIntro(**r.payload) for r in rows]


def save_outreach_log(entry: OutreachLogEntry) -> None:
    engine = get_engine()
    with Session(engine) as s:
        s.merge(
            OutreachLogRow(
                id=entry.id,
                contact_name=entry.contact_name,
                firm=entry.firm,
                job_id=entry.job_id,
                status=entry.status,
                payload=json.loads(entry.model_dump_json()),
                created_at=entry.created_at,
                updated_at=entry.updated_at,
            )
        )
        s.commit()


def load_outreach_log(entry_id: str) -> OutreachLogEntry | None:
    engine = get_engine()
    with Session(engine) as s:
        row = s.get(OutreachLogRow, entry_id)
        return OutreachLogEntry(**row.payload) if row else None


def list_outreach_log(
    status: str | None = None,
    firm: str | None = None,
    job_id: str | None = None,
    limit: int = 200,
) -> list[OutreachLogEntry]:
    engine = get_engine()
    with Session(engine) as s:
        q = s.query(OutreachLogRow)
        if status:
            q = q.filter(OutreachLogRow.status == status)
        if firm:
            q = q.filter(OutreachLogRow.firm == firm)
        if job_id:
            q = q.filter(OutreachLogRow.job_id == job_id)
        rows = q.order_by(OutreachLogRow.updated_at.desc()).limit(limit).all()
        return [OutreachLogEntry(**r.payload) for r in rows]


def delete_outreach_log(entry_id: str) -> bool:
    engine = get_engine()
    with Session(engine) as s:
        row = s.get(OutreachLogRow, entry_id)
        if not row:
            return False
        s.delete(row)
        s.commit()
        return True

# ---------- Contacts (LinkedIn export) -----------------------------------


def upsert_contact(data: dict) -> None:
    """Insert or update a contact by linkedin_url."""
    engine = get_engine()
    with Session(engine) as s:
        existing = s.get(ContactRow, data["linkedin_url"])
        if existing:
            for k, v in data.items():
                if v is not None and k != "linkedin_url":
                    setattr(existing, k, v)
        else:
            s.add(ContactRow(**data))
        s.commit()


def bulk_upsert_contacts(rows: list[dict]) -> int:
    """Bulk upsert; merges fields when contact already exists."""
    engine = get_engine()
    n = 0
    with Session(engine) as s:
        for data in rows:
            existing = s.get(ContactRow, data["linkedin_url"])
            if existing:
                for k, v in data.items():
                    if v is not None and k != "linkedin_url":
                        setattr(existing, k, v)
            else:
                s.add(ContactRow(**data))
            n += 1
        s.commit()
    return n


def update_contact_messaging(
    linkedin_url: str,
    last_message_at: datetime,
    direction: str,
    msg_count_delta: int = 1,
) -> bool:
    engine = get_engine()
    with Session(engine) as s:
        row = s.get(ContactRow, linkedin_url)
        if not row:
            return False
        if row.last_message_at is None or last_message_at > row.last_message_at:
            row.last_message_at = last_message_at
            row.last_message_direction = direction
        row.msg_count = (row.msg_count or 0) + msg_count_delta
        s.commit()
        return True


def update_contact_endorsement(linkedin_url: str, count_delta: int = 1) -> bool:
    engine = get_engine()
    with Session(engine) as s:
        row = s.get(ContactRow, linkedin_url)
        if not row:
            return False
        row.endorsement_count = (row.endorsement_count or 0) + count_delta
        s.commit()
        return True


def update_contact_email_status(
    linkedin_url: str, status: str, note: str | None = None
) -> bool:
    engine = get_engine()
    with Session(engine) as s:
        row = s.get(ContactRow, linkedin_url)
        if not row:
            return False
        row.email_status = status
        row.last_verified_at = datetime.utcnow()
        if note:
            row.notes = (row.notes or "") + f" | verify:{note}"
        s.commit()
        return True


def list_contacts_by_company_norm(company_norm: str) -> list[ContactRow]:
    """Return contacts where company_norm matches.

    Exact match always counts; substring match requires the shorter side to be
    at least 4 chars (prevents 'ib' in 'ibm' false positives).
    """
    engine = get_engine()
    with Session(engine) as s:
        rows = (
            s.query(ContactRow)
            .filter(ContactRow.company_norm.isnot(None))
            .all()
        )
        cn = company_norm.lower().strip()
        if not cn:
            return []
        results = []
        for r in rows:
            cr = r.company_norm
            if not cr:
                continue
            if cr == cn:
                results.append(r)
                continue
            shorter, longer = (cr, cn) if len(cr) < len(cn) else (cn, cr)
            if len(shorter) >= 4 and shorter in longer:
                results.append(r)
        return results


def list_all_contacts(limit: int = 5000) -> list[ContactRow]:
    engine = get_engine()
    with Session(engine) as s:
        return s.query(ContactRow).limit(limit).all()


def list_contacts_with_email(limit: int = 5000) -> list[ContactRow]:
    engine = get_engine()
    with Session(engine) as s:
        return (
            s.query(ContactRow)
            .filter(ContactRow.email.isnot(None))
            .limit(limit)
            .all()
        )


def count_contacts() -> int:
    engine = get_engine()
    with Session(engine) as s:
        return s.query(ContactRow).count()


def upsert_company_follow(organization: str, organization_norm: str, followed_on: datetime | None) -> None:
    engine = get_engine()
    with Session(engine) as s:
        existing = s.get(CompanyFollowRow, organization)
        if existing:
            existing.organization_norm = organization_norm
            if followed_on:
                existing.followed_on = followed_on
        else:
            s.add(CompanyFollowRow(
                organization=organization,
                organization_norm=organization_norm,
                followed_on=followed_on,
            ))
        s.commit()


def list_company_follows() -> list[CompanyFollowRow]:
    engine = get_engine()
    with Session(engine) as s:
        return s.query(CompanyFollowRow).all()


# ---------- Pipeline (per-opportunity funnel) ----------------------------

PIPELINE_STAGES = [
    "discovered",
    "researching",
    "tailored",
    "outreach_sent",
    "reply_received",
    "applied",
    "screen_scheduled",
    "onsite",
    "offer",
    "rejected",
    "ghosted",
    "parked",
]
PIPELINE_TERMINAL = {"offer", "rejected", "ghosted", "parked"}


def pipeline_rank(stage: str) -> int:
    try:
        return PIPELINE_STAGES.index(stage)
    except ValueError:
        return -1


class PipelineRow(Base):
    __tablename__ = "pipeline"
    job_id: Mapped[str] = mapped_column(String, primary_key=True)
    stage: Mapped[str] = mapped_column(String, index=True, default="discovered")
    next_action_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_event_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    notes: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


def get_pipeline(job_id: str) -> PipelineRow | None:
    engine = get_engine()
    with Session(engine) as s:
        return s.get(PipelineRow, job_id)


def upsert_pipeline(
    job_id: str,
    stage: str | None = None,
    next_action_at: datetime | None = None,
    note: str | None = None,
    force_stage: bool = False,
) -> PipelineRow:
    """Insert or update a pipeline entry.

    Stage only moves FORWARD (max rank wins) unless force_stage=True.
    """
    engine = get_engine()
    now = datetime.utcnow()
    with Session(engine) as s:
        row = s.get(PipelineRow, job_id)
        if row is None:
            row = PipelineRow(
                job_id=job_id,
                stage=stage or "discovered",
                next_action_at=next_action_at,
                notes=note,
                last_event_at=now,
                created_at=now,
                updated_at=now,
            )
            s.add(row)
        else:
            if stage and (force_stage or pipeline_rank(stage) > pipeline_rank(row.stage)):
                row.stage = stage
                row.last_event_at = now
            if next_action_at is not None:
                row.next_action_at = next_action_at
            if note:
                prefix = (row.notes + "\n") if row.notes else ""
                row.notes = prefix + f"[{now.strftime('%Y-%m-%d')}] {note}"
            row.updated_at = now
        s.commit()
        s.refresh(row)
        return row


def list_pipeline(
    stage: str | None = None,
    exclude_terminal: bool = False,
    limit: int = 500,
) -> list[PipelineRow]:
    engine = get_engine()
    with Session(engine) as s:
        q = s.query(PipelineRow)
        if stage:
            q = q.filter(PipelineRow.stage == stage)
        if exclude_terminal:
            q = q.filter(~PipelineRow.stage.in_(list(PIPELINE_TERMINAL)))
        return q.order_by(PipelineRow.updated_at.desc()).limit(limit).all()
