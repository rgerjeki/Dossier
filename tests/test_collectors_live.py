"""Opt-in live integration tests for the built-here / wrapped collectors.

Disabled by default; the standard suite never hits the network or shells out.
Enable on demand to re-verify the version-sensitive glue against real services:

    DOSSIER_LIVE=1 pytest tests/test_collectors_live.py

- Gravatar: set DOSSIER_LIVE_EMAIL to a safe email (yours) to run it.
- Metadata: self-contained (creates a temp image and writes tags with exiftool).
- holehe: slow (runs ~120 modules); only runs when DOSSIER_LIVE_EMAIL is set.

Use safe targets only, per the project's legal and ethical rules.
"""

from __future__ import annotations

import os
import shutil
import subprocess

import pytest

if os.environ.get("DOSSIER_LIVE") != "1":
    pytest.skip("live tests disabled (set DOSSIER_LIVE=1)", allow_module_level=True)


def test_github_live() -> None:
    from dossier.collectors.github import GitHubCollector

    run = GitHubCollector().collect("octocat")
    assert run.ok is True
    assert run.findings  # octocat is a real public GitHub user
    assert any("github.com/octocat" in (f.source_url or "") for f in run.findings)


def test_keybase_live() -> None:
    from dossier.collectors.keybase import KeybaseCollector

    run = KeybaseCollector().collect("chris")
    assert run.ok is True
    assert run.findings  # keybase user 'chris' has proven accounts


def test_sec_edgar_live() -> None:
    from dossier.collectors.sec import SECCollector
    from dossier.models import FindingType

    run = SECCollector().collect("Tesla Inc")
    assert run.ok is True
    assert run.findings
    assert all(f.type is FindingType.BUSINESS for f in run.findings)


def test_courtlistener_live() -> None:
    from dossier.collectors.courtlistener import CourtListenerCollector
    from dossier.models import FindingType

    run = CourtListenerCollector().collect("Tesla")
    assert run.ok is True
    assert run.findings
    assert all(f.type is FindingType.LEGAL for f in run.findings)


def test_gravatar_live() -> None:
    email = os.environ.get("DOSSIER_LIVE_EMAIL")
    if not email:
        pytest.skip("set DOSSIER_LIVE_EMAIL to a safe email to run this")

    from dossier.collectors.email import EmailCollector
    from dossier.models import FindingStatus

    run = EmailCollector(use_holehe=False).collect(email)
    assert run.ok is True
    assert run.findings  # at least the avatar present/absent finding
    assert all(
        f.status in (FindingStatus.FOUND, FindingStatus.NOT_FOUND, FindingStatus.UNREACHABLE)
        for f in run.findings
    )


def test_metadata_live(tmp_path) -> None:
    pytest.importorskip("exiftool")
    if shutil.which("exiftool") is None:
        pytest.skip("exiftool binary not on PATH")

    from PySide6.QtGui import QImage

    from dossier.collectors.metadata import MetadataCollector

    img = tmp_path / "photo.jpg"
    QImage(16, 16, QImage.Format.Format_RGB32).save(str(img))
    subprocess.run(
        ["exiftool", "-overwrite_original", "-Make=TestCam", "-Artist=Sample", str(img)],
        check=True,
        capture_output=True,
    )

    run = MetadataCollector().collect(str(img))
    assert run.ok is True
    values = [f.value for f in run.findings]
    assert any("Camera make: TestCam" in v for v in values)
    assert any("Artist: Sample" in v for v in values)


def test_holehe_live() -> None:
    email = os.environ.get("DOSSIER_LIVE_EMAIL")
    if not email:
        pytest.skip("set DOSSIER_LIVE_EMAIL to a safe email to run this (slow)")
    pytest.importorskip("holehe")

    from dossier.collectors.email import EmailCollector

    collector = EmailCollector(use_holehe=True)
    run = collector._run_holehe(email)
    # Every finding is well-formed; existence may or may not be found, that's fine.
    from dossier.models import FindingStatus, FindingType

    for finding in run:
        assert finding.type is FindingType.ACCOUNT
        assert finding.source.startswith("holehe (")
        assert finding.status in (FindingStatus.FOUND, FindingStatus.UNREACHABLE)
