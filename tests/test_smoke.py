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
    embeddings._get_model.cache_clear()  # type: ignore[attr-defined]
    monkeypatch.setattr(embeddings, "_get_model", lambda: None)
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


def test_tailor_no_fabrication_drops_invented_bullets():
    """The validator must drop bullets that don't appear on the profile."""
    from pega_agent.models import ExperienceItem, TailoredBullet, TailoredCV
    from pega_agent.tailor.agent import validate_no_fabrication

    profile = Profile(
        name="Test",
        experience=[
            ExperienceItem(
                company="Acme",
                title="PM",
                start="2020",
                bullets=["Launched new B2C product line, +$1M revenue first year."],
            )
        ],
    )
    cv = TailoredCV(
        job_id="j1",
        language="en",
        headline="h",
        summary="s",
        bullets=[
            TailoredBullet(
                company="Acme",
                original="Launched new B2C product line, +$1M revenue first year.",
                rephrased="Spearheaded 0-to-1 B2C launch generating $1M ARR.",
            ),
            # Hallucinated: company exists but bullet text is invented
            TailoredBullet(
                company="Acme",
                original="Closed a $50M Series B led by Sequoia.",
                rephrased="Closed mega Series B.",
            ),
            # Hallucinated: company doesn't exist on profile
            TailoredBullet(
                company="FakeCo",
                original="Anything.",
                rephrased="Anything.",
            ),
        ],
    )
    cleaned = validate_no_fabrication(cv, profile)
    assert len(cleaned.bullets) == 1
    assert cleaned.bullets[0].company == "Acme"


def test_network_loader_pathing(tmp_path):
    """Direct contact must beat sector-tagged contact for path selection."""
    from pega_agent.models import JobPosting
    from pega_agent.network.loader import (
        find_paths_by_sector,
        find_paths_to_company,
        load_network,
    )

    yaml_path = tmp_path / "network.yaml"
    yaml_path.write_text(
        """
- name: "Ana"
  company: "Falabella"
  strength: 4
  register: es-tu
  tags: ["retail"]
- name: "Beto"
  company: "Cencosud"
  strength: 2
  register: es-usted
  tags: ["retail"]
""".strip(),
        encoding="utf-8",
    )
    contacts = load_network(yaml_path)
    JobPosting(
        id="x", source="x", url="https://x", title="PM", company="Falabella"
    )
    direct = find_paths_to_company("Falabella", contacts)
    assert direct and direct[0].name == "Ana"

    sector = find_paths_by_sector("retail", contacts)
    assert [c.name for c in sector] == ["Ana", "Beto"]


def test_outreach_choose_referral_falls_back_to_cold_when_empty():
    """No contacts → returns None and a default es-usted register."""
    from pega_agent.models import JobPosting
    from pega_agent.outreach.agent import choose_referral

    job = JobPosting(
        id="x", source="x", url="https://x", title="PM", company="Falabella"
    )
    contact, channel, register = choose_referral(job, [])
    assert contact is None
    assert channel == "linkedin_dm"
    assert register == "es-usted"


# ---------- Phase 5 ------------------------------------------------------


def test_interview_prep_validator_drops_invented_stars():
    """STAR stories whose source bullet doesn't match the profile are dropped."""
    from pega_agent.interview.agent import validate_stars
    from pega_agent.models import ExperienceItem, STARStory

    profile = Profile(
        name="Test",
        experience=[
            ExperienceItem(
                company="Acme",
                title="PM",
                start="2020",
                bullets=["Launched new B2C product line, +$1M revenue first year."],
            )
        ],
    )
    real = STARStory(
        theme="0-to-1",
        title="B2C launch",
        situation="Acme had no B2C SKU.",
        task="Build and ship the first.",
        action="Stood up the team, picked the segment, ran 4 experiments.",
        result="$1M ARR year 1.",
        source_company="Acme",
        source_bullet="Launched new B2C product line, +$1M revenue first year.",
    )
    invented = STARStory(
        theme="leadership",
        title="Series B",
        situation="x",
        task="x",
        action="x",
        result="x",
        source_company="Acme",
        source_bullet="Closed a $50M Series B led by Sequoia.",  # not in profile
    )
    out = validate_stars([real, invented], profile)
    assert len(out) == 1
    assert out[0].title == "B2C launch"


def test_negotiation_draft_roundtrip():
    """NegotiationDraft must serialize / deserialize cleanly."""
    from pega_agent.models import CompBenchmark, NegotiationDraft

    bench = CompBenchmark(
        role="Director of Product",
        seniority="director",
        sector="retail",
        base_low_clp=8_000_000,
        base_mid_clp=10_500_000,
        base_high_clp=13_000_000,
        variable_pct=20.0,
    )
    neg = NegotiationDraft(
        job_id="abc",
        offer_base_clp=9_500_000,
        target_base_clp=11_000_000,
        walk_away_clp=10_000_000,
        benchmark=bench,
        levers_to_negotiate=["bono garantizado año 1", "sign-on 8M", "20 días vacaciones"],
        rationale="Offer below mid; modest counter justified.",
        counter_email_body="Estimado/a, gracias por la oferta…",
    )
    blob = neg.model_dump_json()
    again = NegotiationDraft.model_validate_json(blob)
    assert again.target_base_clp == 11_000_000
    assert again.benchmark and again.benchmark.base_mid_clp == 10_500_000
    assert again.language == "es"


def test_interview_prep_db_roundtrip(tmp_path, monkeypatch):
    """save_interview_prep → load_interview_prep via SQLite."""
    monkeypatch.setattr(
        "pega_agent.config.settings.pega_db_path", tmp_path / "pega.sqlite"
    )
    import importlib

    import pega_agent.db as db

    importlib.reload(db)
    from pega_agent.models import InterviewPrepPack, STARStory

    pack = InterviewPrepPack(
        job_id="j-prep",
        language="es",
        company_angle="NotCo necesita un Director de Producto con experiencia 0-to-1.",
        star_stories=[
            STARStory(
                theme="0-to-1",
                title="Lanzamiento",
                situation="s",
                task="t",
                action="a",
                result="r",
                source_company="Acme",
                source_bullet="Launched new B2C product line, +$1M revenue first year.",
                language="es",
            )
        ],
        questions_to_ask=["¿Cómo se mide el éxito de este rol a los 6 meses?"],
        likely_questions=["Cuéntame de tu falla más reciente."],
    )
    db.save_interview_prep(pack)
    got = db.load_interview_prep("j-prep")
    assert got is not None
    assert got.language == "es"
    assert len(got.star_stories) == 1
    assert got.star_stories[0].theme == "0-to-1"
