"""Tests for the Maigret collector's normalization and graceful degradation.

No network and no Maigret: the live adapter (``_run_maigret``) is stubbed. What
is verified here is the mapping that carries the tool's meaning into findings.
"""

from __future__ import annotations

from dossier.collectors.base import Collector
from dossier.collectors.usernames import (
    MaigretCollector,
    MaigretNotInstalled,
    SiteResult,
    normalize,
)
from dossier.models import Confidence, FindingStatus, FindingType


def test_normalize_surfaces_only_leads_and_unreachable() -> None:
    sites = [
        SiteResult("GitHub", "https://github.com/ex", exists=True),
        SiteResult("Reddit", "https://reddit.com/u/ex", exists=False),  # absent, dropped
        SiteResult("Twitter", None, exists=None, error=True),  # unreachable, kept
    ]
    findings = normalize("ex", sites)

    assert len(findings) == 2
    lead, unreachable = findings

    assert lead.type is FindingType.ACCOUNT
    assert lead.status is FindingStatus.FOUND
    assert lead.source_confidence is Confidence.HIGH
    assert lead.value == "https://github.com/ex"
    assert lead.source == "Maigret (GitHub)"

    assert unreachable.status is FindingStatus.UNREACHABLE
    assert unreachable.source_confidence is Confidence.UNKNOWN
    assert unreachable.value == "Twitter (ex)"  # falls back to a readable label


def test_collect_reports_summary(monkeypatch) -> None:
    collector = MaigretCollector()
    monkeypatch.setattr(
        collector,
        "_run_maigret",
        lambda username: [
            SiteResult("GitHub", "https://github.com/ex", exists=True),
            SiteResult("Keybase", "https://keybase.io/ex", exists=True),
            SiteResult("Foo", None, exists=None, error=True),
        ],
    )
    run = collector.collect("ex")

    assert run.ok is True
    assert len(run.findings) == 3
    assert "3 site(s)" in run.message
    assert "2 lead(s)" in run.message
    assert "1 unreachable" in run.message


def test_collect_handles_missing_maigret(monkeypatch) -> None:
    collector = MaigretCollector()

    def _boom(username: str):
        raise MaigretNotInstalled

    monkeypatch.setattr(collector, "_run_maigret", _boom)
    run = collector.collect("ex")

    assert run.ok is False
    assert not run.findings
    assert "not installed" in run.message


def test_collect_handles_run_failure(monkeypatch) -> None:
    collector = MaigretCollector()

    def _boom(username: str):
        raise RuntimeError("network exploded")

    monkeypatch.setattr(collector, "_run_maigret", _boom)
    run = collector.collect("ex")

    assert run.ok is False
    assert "network exploded" in run.message


def test_empty_username_is_rejected() -> None:
    run = MaigretCollector().collect("   ")
    assert run.ok is False
    assert "No username" in run.message


def test_maigret_collector_is_a_collector() -> None:
    assert isinstance(MaigretCollector(), Collector)
