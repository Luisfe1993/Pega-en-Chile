from __future__ import annotations

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
