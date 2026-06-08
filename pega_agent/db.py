from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from pega_agent.config import settings
from pega_agent.models import (
    ApprovalDecision,
    CompanyBrief,
    CoverLetter,
    JobPosting,
    MatchScore,
    OutreachDraft,
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
