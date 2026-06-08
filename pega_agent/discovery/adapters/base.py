from __future__ import annotations

from abc import ABC, abstractmethod

from pega_agent.models import JobPosting


class JobSource(ABC):
    """Common interface every board adapter implements."""

    name: str

    @abstractmethod
    def search(
        self,
        query: str,
        location: str = "Santiago, Chile",
        limit: int = 50,
    ) -> list[JobPosting]: ...
