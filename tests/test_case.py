"""Engine tests for the Case model and its JSON storage. No Qt, no network."""

from __future__ import annotations

from pathlib import Path

import dossier.case as case_mod
from dossier.case import Case, SubjectType, app_data_dir, default_cases_dir
from dossier.models import Finding, FindingType


def test_cases_dir_env_override_wins(monkeypatch) -> None:
    monkeypatch.setenv("DOSSIER_CASES_DIR", "/tmp/dossier-cases")
    assert default_cases_dir() == Path("/tmp/dossier-cases")


def test_cases_dir_dev_is_cwd_relative(monkeypatch) -> None:
    monkeypatch.delenv("DOSSIER_CASES_DIR", raising=False)
    monkeypatch.setattr(case_mod, "_is_frozen", lambda: False)
    assert default_cases_dir() == Path("cases")


def test_cases_dir_frozen_uses_user_data_dir(monkeypatch) -> None:
    monkeypatch.delenv("DOSSIER_CASES_DIR", raising=False)
    monkeypatch.setattr(case_mod, "_is_frozen", lambda: True)
    # A packaged app must not write beside the bundle; it uses the user-data dir.
    assert default_cases_dir() == app_data_dir() / "cases"


def _make_case() -> Case:
    return Case(
        subject="example_user",
        subject_type=SubjectType.USERNAME,
        analyst="Reese",
        authorized=True,
        scope_note="Safe target (self). Public, passive collection only.",
    )


def test_title_defaults_to_subject() -> None:
    case = Case(subject="example_user", subject_type="username")
    assert case.title == "example_user"
    assert case.subject_type is SubjectType.USERNAME


def test_included_findings_filters() -> None:
    case = _make_case()
    kept = Finding(type=FindingType.ACCOUNT, value="a", source="s", included=True)
    dropped = Finding(type=FindingType.ACCOUNT, value="b", source="s", included=False)
    case.add_finding(kept)
    case.add_finding(dropped)
    assert case.included_findings() == [kept]


def test_add_finding_bumps_updated_at() -> None:
    case = _make_case()
    before = case.updated_at
    case.add_finding(Finding(type=FindingType.EMAIL, value="e", source="s"))
    assert case.updated_at >= before
    assert len(case.findings) == 1


def test_save_and_load_round_trip(tmp_path) -> None:
    case = _make_case()
    case.add_finding(Finding(type=FindingType.ACCOUNT, value="a", source="Maigret"))
    path = case.save(tmp_path)

    assert path.exists()
    assert path.parent == tmp_path

    loaded = Case.load(path)
    assert loaded.to_dict() == case.to_dict()
    assert loaded.authorized is True
    assert loaded.scope_note == case.scope_note
    assert len(loaded.findings) == 1


def test_default_cases_dir_env_override(tmp_path, monkeypatch) -> None:
    from dossier import case as case_module

    monkeypatch.setenv("DOSSIER_CASES_DIR", str(tmp_path / "vault"))
    assert case_module.default_cases_dir() == tmp_path / "vault"
