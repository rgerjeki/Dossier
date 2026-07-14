"""Offline tests for the API data collectors (GitHub, Keybase, SEC, CourtListener).

The network-bound fetch is injected, so only normalization and graceful
degradation are exercised. Live checks live in test_collectors_live.py.
"""

from __future__ import annotations

from dossier.collectors.courtlistener import CourtListenerCollector
from dossier.collectors.github import GitHubCollector
from dossier.collectors.keybase import KeybaseCollector
from dossier.collectors.sec import SECCollector
from dossier.models import FindingType


def _fetch(status, data):
    return lambda url: (status, data)


# --- GitHub ---------------------------------------------------------------


def test_github_normalizes_profile() -> None:
    profile = {
        "html_url": "https://github.com/ex",
        "name": "Example User",
        "company": "Acme",
        "location": "NYC",
        "email": "ex@example.com",
        "blog": "example.com",
        "twitter_username": "exhandle",
    }
    run = GitHubCollector(fetch=_fetch(200, profile)).collect("ex")
    types = {f.type for f in run.findings}
    values = " ".join(f.value for f in run.findings)
    assert FindingType.ACCOUNT in types and FindingType.EMAIL in types
    assert FindingType.LINK in types  # website
    assert "github.com/ex" in values
    assert "ex@example.com" in values
    assert "https://example.com" in values  # blog normalized to https
    assert "x.com/exhandle" in values


def test_github_missing_user_is_ok_empty() -> None:
    run = GitHubCollector(fetch=_fetch(404, None)).collect("nobody")
    assert run.ok is True and run.findings == []


def test_github_rate_limit_reported() -> None:
    run = GitHubCollector(fetch=_fetch(403, None)).collect("ex")
    assert run.ok is False and "rate limit" in run.message


# --- Keybase --------------------------------------------------------------


def test_keybase_normalizes_proofs() -> None:
    data = {
        "them": [
            {
                "proofs_summary": {
                    "all": [
                        {"proof_type": "twitter", "nametag": "h", "service_url": "https://x/h"},
                        {"proof_type": "dns", "nametag": "ex.com", "service_url": "http://ex.com"},
                    ]
                }
            }
        ]
    }
    run = KeybaseCollector(fetch=_fetch(200, data)).collect("ex")
    assert len(run.findings) == 2
    assert any(f.type is FindingType.ACCOUNT for f in run.findings)
    assert any(f.type is FindingType.LINK for f in run.findings)  # website proof


def test_keybase_no_user() -> None:
    run = KeybaseCollector(fetch=_fetch(200, {"them": []})).collect("ex")
    assert run.ok is True and "No Keybase user" in run.message


# --- SEC EDGAR ------------------------------------------------------------


def test_sec_normalizes_and_dedupes_entities() -> None:
    hits = [
        {"_source": {"display_names": ["Tesla, Inc.  (CIK 0001318605)"]}},
        {"_source": {"display_names": [
            "Tesla, Inc.  (CIK 0001318605)", "Jane Doe  (CIK 0000000123)"]}},
    ]
    run = SECCollector(fetch=_fetch(200, {"hits": {"hits": hits}})).collect("Tesla")
    assert all(f.type is FindingType.BUSINESS for f in run.findings)
    assert len(run.findings) == 2  # deduped Tesla + Jane Doe
    assert any("CIK=0001318605" in (f.source_url or "") for f in run.findings)


def test_sec_no_hits() -> None:
    run = SECCollector(fetch=_fetch(200, {"hits": {"hits": []}})).collect("nothing")
    assert run.ok is True and run.findings == []


# --- CourtListener --------------------------------------------------------


def test_courtlistener_normalizes_opinions() -> None:
    data = {
        "count": 2,
        "results": [
            {"caseName": "Doe v. Acme", "court": "9th Cir.", "dateFiled": "2020-01-01",
             "absolute_url": "/opinion/1/doe/"},
        ],
    }
    run = CourtListenerCollector(fetch=_fetch(200, data)).collect("Acme")
    assert run.findings[0].type is FindingType.LEGAL
    assert "Doe v. Acme" in run.findings[0].value
    assert run.findings[0].source_url == "https://www.courtlistener.com/opinion/1/doe/"


def test_courtlistener_rate_limit() -> None:
    run = CourtListenerCollector(fetch=_fetch(429, None)).collect("x")
    assert run.ok is False and "rate limit" in run.message
