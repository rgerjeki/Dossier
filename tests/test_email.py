"""Tests for the email collector. Gravatar via a mock fetch; holehe mapping mocked.

No network and no holehe run: the network-bound ``_run_holehe`` adapter is stubbed
so only the mapping and degradation behavior are exercised.
"""

from __future__ import annotations

import hashlib

from dossier.collectors.email import (
    EmailCollector,
    _holehe_findings,
    _HoleheUnavailable,
    gravatar_findings,
    gravatar_hash,
)
from dossier.models import FindingStatus, FindingType


def test_gravatar_hash_is_sha256_of_normalized_email() -> None:
    expected = hashlib.sha256(b"user@example.com").hexdigest()
    assert gravatar_hash("  User@Example.COM ") == expected


def _fetch_factory(avatar_status: int, profile: dict | None):
    def fetch(url: str):
        if "/avatar/" in url:
            return (avatar_status, None)
        if url.endswith(".json"):
            return (200 if profile is not None else 404, profile)
        return (404, None)

    return fetch


def test_gravatar_avatar_and_profile() -> None:
    profile = {
        "entry": [
            {
                "displayName": "Reese G",
                "accounts": [{"shortname": "github", "url": "https://github.com/rg"}],
            }
        ]
    }
    findings = gravatar_findings("e@example.com", _fetch_factory(200, profile))
    values = [f.value for f in findings]
    assert any("avatar exists" in v for v in values)
    assert any("display name: Reese G" in v for v in values)
    assert any("Linked github" in v for v in values)


def test_gravatar_absent() -> None:
    findings = gravatar_findings("e@example.com", _fetch_factory(404, None))
    assert findings[0].status is FindingStatus.NOT_FOUND


def test_gravatar_network_error_is_unreachable() -> None:
    def boom(url: str):
        raise ConnectionError("no network")

    findings = gravatar_findings("e@example.com", boom)
    assert len(findings) == 1
    assert findings[0].status is FindingStatus.UNREACHABLE


def test_holehe_findings_mapping() -> None:
    raw = [
        {"name": "wordpress", "exists": True, "rateLimit": False},
        {"name": "atlassian", "exists": False, "rateLimit": True},  # unreachable
        {"name": "spotify", "exists": False, "rateLimit": False},  # absent, dropped
    ]
    findings = _holehe_findings("e@example.com", raw)
    assert len(findings) == 2
    found = [f for f in findings if f.status is FindingStatus.FOUND]
    assert found[0].type is FindingType.ACCOUNT
    assert "wordpress" in found[0].source
    assert any(f.status is FindingStatus.UNREACHABLE for f in findings)


def test_collector_rejects_non_email() -> None:
    run = EmailCollector(use_holehe=False).collect("not-an-email")
    assert run.ok is False
    assert "valid email" in run.message


def test_collector_gravatar_only(monkeypatch) -> None:
    collector = EmailCollector(fetch=_fetch_factory(200, None), use_holehe=False)
    run = collector.collect("e@example.com")
    assert run.ok is True
    assert any("avatar exists" in f.value for f in run.findings)


def test_collector_notes_when_holehe_missing() -> None:
    collector = EmailCollector(fetch=_fetch_factory(200, None), use_holehe=True)

    def _unavailable(email: str):
        raise _HoleheUnavailable

    collector._run_holehe = _unavailable  # type: ignore[method-assign]
    run = collector.collect("e@example.com")
    assert run.ok is True
    assert "holehe not installed" in run.message


def test_collector_merges_holehe_findings() -> None:
    collector = EmailCollector(fetch=_fetch_factory(404, None), use_holehe=True)

    def _fake(email: str):
        return _holehe_findings(email, [{"name": "wp", "exists": True, "rateLimit": False}])

    collector._run_holehe = _fake  # type: ignore[method-assign]
    run = collector.collect("e@example.com")
    assert any("Account exists at wp" in f.value for f in run.findings)
