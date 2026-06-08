"""Network loader. Reads `data/network.yaml` → list[NetworkContact]."""

from __future__ import annotations

from pathlib import Path

import yaml

from pega_agent.config import ROOT
from pega_agent.models import NetworkContact

DEFAULT_NETWORK_PATH = ROOT / "data" / "network.yaml"


def load_network(path: Path = DEFAULT_NETWORK_PATH) -> list[NetworkContact]:
    if not path.exists():
        return []
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    return [NetworkContact(**item) for item in raw]


def find_paths_to_company(
    company: str, contacts: list[NetworkContact]
) -> list[NetworkContact]:
    """Direct contacts at the target company (sorted by strength desc)."""
    needle = company.strip().lower()
    matches = [
        c for c in contacts if c.company and needle in c.company.strip().lower()
    ]
    matches.sort(key=lambda c: c.strength, reverse=True)
    return matches


def find_paths_by_sector(
    sector: str, contacts: list[NetworkContact]
) -> list[NetworkContact]:
    """Contacts tagged with a given sector (fallback for indirect intros)."""
    s = sector.lower()
    return sorted(
        [c for c in contacts if any(s in t.lower() for t in c.tags)],
        key=lambda c: c.strength,
        reverse=True,
    )
