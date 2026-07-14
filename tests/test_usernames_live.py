"""Opt-in live integration test for the Maigret adapter.

The default suite never hits the network. This test only runs when you explicitly
ask for it, so the Maigret glue (which is version-sensitive) can be re-verified
against a real install on demand:

    DOSSIER_LIVE=1 DOSSIER_LIVE_USERNAME=<a-safe-handle> pytest tests/test_usernames_live.py

Use a safe target only (yourself, a public figure, a seeded persona, or a
sanctioned CTF), per the project's legal and ethical rules. The handle is taken
from the environment so no personal data is baked into the repo.
"""

from __future__ import annotations

import os

import pytest

if os.environ.get("DOSSIER_LIVE") != "1":
    pytest.skip("live test disabled (set DOSSIER_LIVE=1)", allow_module_level=True)

pytest.importorskip("maigret")

from dossier.collectors.usernames import MaigretCollector  # noqa: E402
from dossier.models import FindingStatus, FindingType  # noqa: E402


def test_live_maigret_returns_real_findings() -> None:
    username = os.environ.get("DOSSIER_LIVE_USERNAME")
    if not username:
        pytest.skip("set DOSSIER_LIVE_USERNAME to a safe handle to run this")

    run = MaigretCollector(top_sites=25, timeout=20).collect(username)

    assert run.ok is True
    assert "site(s)" in run.message
    # Every finding is well-formed and carries provenance.
    for finding in run.findings:
        assert finding.type is FindingType.ACCOUNT
        assert finding.source.startswith("Maigret (")
        assert finding.status in (FindingStatus.FOUND, FindingStatus.UNREACHABLE)
        if finding.status is FindingStatus.FOUND:
            assert finding.value  # a URL or a readable label
