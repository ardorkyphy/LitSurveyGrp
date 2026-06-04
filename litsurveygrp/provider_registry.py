# -*- coding: utf-8 -*-
"""Registry for journal discovery providers.

The downloader should not need to know every concrete discovery backend. This
module keeps provider construction explicit and replaceable while preserving the
simple provider-name contract used by the CLI and journal catalog.
"""

from dataclasses import dataclass
from typing import Any, Callable, Protocol


class DiscoveryProvider(Protocol):
    """Provider protocol for sources that discover article records."""

    def discover(self) -> list:
        """Return discovered article records."""


@dataclass(frozen=True)
class ProviderBuildContext:
    """Shared runtime options passed to provider factories."""

    year: int | None = None
    from_year: int | None = None
    to_year: int | None = None
    limit: int | None = None
    timeout: int = 15


ProviderFactory = Callable[[Any, ProviderBuildContext], DiscoveryProvider]


class JournalProviderRegistry:
    """Map provider names to factories.

    New metadata/API/crawler layers can be added by registering another factory
    instead of editing the download service orchestration.
    """

    def __init__(self):
        self._factories: dict[str, ProviderFactory] = {}

    def register(self, name: str, factory: ProviderFactory) -> None:
        """Register one provider factory."""
        key = self._normalize_name(name)
        if not key:
            raise ValueError("provider name cannot be empty")
        self._factories[key] = factory

    def create(self, name: str, journal_config: Any, context: ProviderBuildContext) -> DiscoveryProvider:
        """Build a provider by name."""
        key = self._normalize_name(name)
        try:
            factory = self._factories[key]
        except KeyError as exc:
            raise ValueError(f"unsupported journal provider: {name}") from exc
        return factory(journal_config, context)

    def names(self) -> tuple[str, ...]:
        """Return registered provider names."""
        return tuple(sorted(self._factories))

    def _normalize_name(self, name: str) -> str:
        return (name or "").strip().casefold()
