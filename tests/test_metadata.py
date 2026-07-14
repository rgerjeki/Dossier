"""Tests for the metadata collector. ``normalize`` is pure; no ExifTool needed."""

from __future__ import annotations

from dossier.collectors.base import Collector
from dossier.collectors.metadata import MetadataCollector, normalize
from dossier.models import Confidence, FindingStatus, FindingType


def test_normalize_surfaces_tags_of_interest() -> None:
    tags = {
        "SourceFile": "/tmp/photo.jpg",
        "EXIF:Make": "TestCam",
        "EXIF:Model": "DX100",
        "EXIF:Artist": "Reese",
        "Composite:GPSPosition": "40.0 N, 73.0 W",
        "EXIF:MegaPixels": 12,  # not of interest, ignored
    }
    findings = normalize("/tmp/photo.jpg", tags)
    values = [f.value for f in findings]
    assert "Camera make: TestCam" in values
    assert "Camera model: DX100" in values
    assert "Artist: Reese" in values
    assert any("GPS position" in v for v in values)
    assert not any("MegaPixels" in v for v in values)
    for finding in findings:
        assert finding.type is FindingType.METADATA
        assert finding.status is FindingStatus.FOUND
        assert finding.source_confidence is Confidence.HIGH
        assert "photo.jpg" in finding.source


def test_normalize_skips_empty_values() -> None:
    findings = normalize("/tmp/x.jpg", {"EXIF:Make": "", "EXIF:Model": None})
    assert findings == []


def test_collect_missing_file() -> None:
    run = MetadataCollector().collect("/no/such/file.jpg")
    assert run.ok is False
    assert "not found" in run.message


def test_collect_empty_target() -> None:
    run = MetadataCollector().collect("  ")
    assert run.ok is False


def test_is_a_collector() -> None:
    assert isinstance(MetadataCollector(), Collector)
