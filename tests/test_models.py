"""Engine tests for the Finding model. No Qt, no network."""

from __future__ import annotations

from dossier.models import (
    SECTION_ACCOUNTS,
    Confidence,
    Finding,
    FindingStatus,
    FindingType,
    default_section_for_type,
)


def test_defaults_section_from_type() -> None:
    f = Finding(
        type=FindingType.ACCOUNT,
        value="https://github.com/example",
        source="Maigret (github.com)",
    )
    assert f.report_section == SECTION_ACCOUNTS
    assert f.status is FindingStatus.FOUND
    assert f.source_confidence is Confidence.UNKNOWN
    assert f.analyst_confidence is Confidence.UNKNOWN
    assert f.included is False
    assert f.id  # auto-assigned


def test_accepts_plain_strings_for_enum_fields() -> None:
    f = Finding(
        type="email",
        value="test@example.com",
        source="Gravatar",
        status="unreachable",
        source_confidence="low",
    )
    assert f.type is FindingType.EMAIL
    assert f.status is FindingStatus.UNREACHABLE
    assert f.source_confidence is Confidence.LOW


def test_round_trip_serialization() -> None:
    original = Finding(
        type=FindingType.METADATA,
        value="GPS: 40.0, -73.0",
        source="ExifTool (photo.jpg)",
        source_url=None,
        status=FindingStatus.FOUND,
        source_confidence=Confidence.CONFIRMED,
        analyst_confidence=Confidence.HIGH,
        included=True,
        notes="Location looks consistent with other findings.",
    )
    restored = Finding.from_dict(original.to_dict())
    assert restored.to_dict() == original.to_dict()
    assert restored.id == original.id
    assert restored.collected_at == original.collected_at


def test_explicit_section_override_survives_round_trip() -> None:
    f = Finding(
        type=FindingType.LINK,
        value="https://www.google.com/search?q=...",
        source="Search-kit",
        report_section="Custom Section",
    )
    assert f.report_section == "Custom Section"
    assert Finding.from_dict(f.to_dict()).report_section == "Custom Section"


def test_default_section_mapping_is_total() -> None:
    for t in FindingType:
        assert default_section_for_type(t)
