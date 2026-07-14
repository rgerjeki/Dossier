"""File and photo metadata collector (wraps ExifTool via PyExifTool).

Runs locally on a supplied file, so it always returns real data with no network
dependency. The raw ExifTool read is isolated in ``_read_metadata``; the mapping
to findings lives in ``normalize`` and is unit-tested without ExifTool installed.

Findings of interest are surfaced individually (GPS, camera, timestamps, author),
because in an investigation those are the pivots. The full tag dump is not turned
into hundreds of findings.
"""

from __future__ import annotations

from pathlib import Path

from ..models import Confidence, Finding, FindingStatus, FindingType
from .base import Collector, CollectorRun

# ExifTool tag -> (human label). These are the investigation-relevant ones.
_TAGS_OF_INTEREST: list[tuple[str, str]] = [
    ("EXIF:GPSLatitude", "GPS latitude"),
    ("EXIF:GPSLongitude", "GPS longitude"),
    ("Composite:GPSPosition", "GPS position"),
    ("EXIF:DateTimeOriginal", "Capture time"),
    ("EXIF:CreateDate", "Create date"),
    ("EXIF:Make", "Camera make"),
    ("EXIF:Model", "Camera model"),
    ("EXIF:LensModel", "Lens"),
    ("EXIF:SerialNumber", "Camera serial"),
    ("EXIF:Artist", "Artist"),
    ("EXIF:Copyright", "Copyright"),
    ("XMP:Creator", "Creator"),
    ("XMP:CreatorTool", "Creator tool"),
    ("PDF:Author", "Author"),
    ("PDF:Creator", "PDF creator"),
    ("PDF:Producer", "PDF producer"),
    ("IPTC:By-line", "By-line"),
]


class ExifToolNotAvailable(RuntimeError):
    """Raised when PyExifTool or the exiftool binary is not available."""


def normalize(path: str, tags: dict) -> list[Finding]:
    """Map an ExifTool tag dict to findings for the interesting tags."""

    name = Path(path).name
    findings: list[Finding] = []
    for tag, label in _TAGS_OF_INTEREST:
        if tag in tags and tags[tag] not in (None, ""):
            findings.append(
                Finding(
                    type=FindingType.METADATA,
                    value=f"{label}: {tags[tag]}",
                    source=f"ExifTool ({name}, {tag})",
                    status=FindingStatus.FOUND,
                    source_confidence=Confidence.HIGH,
                )
            )
    return findings


class MetadataCollector(Collector):
    """Extracts EXIF / file metadata from a local file using ExifTool."""

    name = "File metadata (ExifTool)"

    def collect(self, target: str) -> CollectorRun:
        path = target.strip()
        if not path:
            return CollectorRun(self.name, ok=False, message="No file provided.")
        if not Path(path).is_file():
            return CollectorRun(self.name, ok=False, message=f"File not found: {path}")

        try:
            tags = self._read_metadata(path)
        except ExifToolNotAvailable:
            return CollectorRun(
                self.name,
                ok=False,
                message=(
                    "ExifTool is not available. Install the exiftool binary and:\n"
                    '    pip install -e ".[collectors]"'
                ),
            )
        except Exception as exc:  # noqa: BLE001 - honest degradation
            return CollectorRun(self.name, ok=False, message=f"ExifTool failed: {exc}")

        findings = normalize(path, tags)
        return CollectorRun(
            self.name,
            findings=findings,
            ok=True,
            message=f"Read metadata from {Path(path).name}: {len(findings)} of interest.",
        )

    def _read_metadata(self, path: str) -> dict:
        """Read all tags for one file. Isolated adapter over PyExifTool."""

        try:
            import exiftool
        except ImportError as exc:
            raise ExifToolNotAvailable from exc

        try:
            with exiftool.ExifToolHelper() as et:
                results = et.get_metadata([path])
        except FileNotFoundError as exc:  # exiftool binary missing on PATH
            raise ExifToolNotAvailable from exc
        return results[0] if results else {}
