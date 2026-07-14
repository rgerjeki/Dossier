"""The collector contract shared by every collector.

A collector wraps one source (or one wrapped tool) and returns a
``CollectorRun``: the findings it produced plus an honest, collector-level status.
Per-site outcomes live on each ``Finding`` (via ``FindingStatus``); the run-level
``ok``/``message`` covers the whole-collector cases the UI must not hide, such as
"the wrapped tool is not installed" or "the run failed before it started".

This module is pure stdlib so the engine and its tests never import Qt or any
wrapped collector.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from ..models import Finding


@dataclass
class CollectorRun:
    """The outcome of one collector run.

    Attributes:
        collector: Human-readable collector name, for display and citation.
        findings: The normalized findings produced (may be empty).
        ok: True if the collector ran to completion. False means it could not run
            or failed outright (see ``message``); this is never hidden from the
            investigator.
        message: A short, honest status line for the UI (for example
            "Checked 500 sites, 3 leads." or "Maigret is not installed.").
    """

    collector: str
    findings: list[Finding] = field(default_factory=list)
    ok: bool = True
    message: str = ""


class Collector(ABC):
    """Base class for all collectors.

    Subclasses set ``name`` and implement ``collect``. Implementations must
    degrade gracefully: a missing wrapped tool, a network block, or a rate limit
    returns a ``CollectorRun`` (with ``ok=False`` or per-finding statuses), never
    an unhandled exception.
    """

    name: str = "collector"

    @abstractmethod
    def collect(self, target: str) -> CollectorRun:
        """Run the collector against ``target`` and return a normalized run."""
        raise NotImplementedError
