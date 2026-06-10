"""Search spec IO. The search.yaml file expresses what the user wants.

Keep this module dependency-light; the Matcher and CLI both import from it.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from pega_agent.models import Search


def load_search(path: Path) -> Search:
    if not path.exists():
        # Sensible default: a fresh user gets the example.
        return Search()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return Search(**data)


def save_search(search: Search, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            search.model_dump(exclude_none=True), sort_keys=False, allow_unicode=True
        ),
        encoding="utf-8",
    )
