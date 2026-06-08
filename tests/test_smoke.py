from __future__ import annotations

from pega_agent.matcher import embeddings
from pega_agent.matcher.agent import score_job
from pega_agent.models import JobPosting, Profile


def test_score_job_basic_overlap():
    profile = Profile(
        name="Test",
        target_roles=["product manager"],
        target_seniority="manager",
        target_sectors=["energy"],
        skills=["product management", "ai", "sql", "agile", "okrs"],
        locations_open_to=["Santiago, CL"],
    )
    job = JobPosting(
        id="abc",
        source="getonboard",
        url="https://example.com/x",
        title="Product Manager - AI",
        company="Acme Energy",
        location="Santiago, CL",
        description="Looking for product manager with AI, SQL and Agile experience in energy.",
    )
    s = score_job(profile, job)
    assert 0 <= s.score <= 100
    assert s.skill_overlap > 0
    assert s.seniority_fit == 1.0
    assert s.location_fit == 1.0


def test_score_job_irrelevant():
    profile = Profile(
        name="Test",
        target_seniority="manager",
        skills=["product management"],
        target_sectors=["energy"],
        locations_open_to=["Santiago, CL"],
    )
    job = JobPosting(
        id="z",
        source="getonboard",
        url="https://example.com/z",
        title="Welder",
        company="Mining co",
        location="Antofagasta",
        description="Welding role in mine",
    )
    s = score_job(profile, job)
    assert s.score < 30


def test_embeddings_degraded_mode(monkeypatch):
    """When the model can't load, semantic_fit must be 0 and the score still in range."""
    monkeypatch.setattr(embeddings, "_get_model", lambda: None)
    embeddings._get_model.cache_clear()  # type: ignore[attr-defined]
    profile = Profile(
        name="Test",
        target_seniority="manager",
        skills=["product management"],
        locations_open_to=["Santiago, CL"],
    )
    job = JobPosting(
        id="d",
        source="x",
        url="https://example.com/d",
        title="Product Manager",
        company="Foo",
        location="Santiago, CL",
        description="PM role",
    )
    s = score_job(profile, job)
    assert s.semantic_fit == 0.0
    assert 0 <= s.score <= 100


def test_research_cache_roundtrip(tmp_path, monkeypatch):
    """save_brief → load_brief must roundtrip via SQLite."""
    monkeypatch.setattr(
        "pega_agent.config.settings.pega_db_path", tmp_path / "pega.sqlite"
    )
    # re-import to bind the patched path
    import importlib

    import pega_agent.db as db

    importlib.reload(db)
    from pega_agent.models import CompanyBrief

    brief = CompanyBrief(company="Acme", what_they_do="Stuff", sector="Energy")
    db.save_brief(brief)
    got = db.load_brief("acme")
    assert got is not None
    assert got.company == "Acme"
    assert got.what_they_do == "Stuff"
