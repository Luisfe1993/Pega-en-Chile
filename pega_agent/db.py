from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from pega_agent.config import settings
from pega_agent.models import JobPosting, MatchScore


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
