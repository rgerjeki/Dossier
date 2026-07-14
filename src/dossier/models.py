"""The normalized data model that every collector produces and the report consumes.

A ``Finding`` is the single unit of currency in Dossier. Every collector, no
matter what tool it wraps, returns a list of ``Finding`` objects in this shape.
The curation view marks which ones to include, and the report renders included
findings into their sections and cites each one from its ``source``.

This module is pure stdlib on purpose: the engine must import and test without
Qt or any collector installed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4


class FindingType(StrEnum):
    """What kind of thing a finding is. Also drives its default report section."""

    ACCOUNT = "account"  # a presence on a site/platform (e.g. a username hit)
    EMAIL = "email"  # an email account-existence or Gravatar result
    METADATA = "metadata"  # EXIF / file metadata extracted from media
    LINK = "link"  # a guided pivot link or other lead to review by hand
    BUSINESS = "business"  # a company/registration/filing record (e.g. SEC EDGAR)
    LEGAL = "legal"  # a court, litigation, or legal record (e.g. CourtListener)


class FindingStatus(StrEnum):
    """The honest outcome of trying to collect this finding.

    This is what makes graceful degradation real instead of aspirational: a
    collector that was blocked, rate limited, or unreachable is recorded as such,
    never silently dropped.
    """

    FOUND = "found"  # confirmed present
    NOT_FOUND = "not_found"  # checked, confirmed absent
    UNREACHABLE = "unreachable"  # blocked, rate limited, or timed out
    NOT_RUN = "not_run"  # collector did not execute (missing dep, skipped)


class Confidence(StrEnum):
    """A graded confidence level, used for both source and analyst assessments."""

    UNKNOWN = "unknown"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CONFIRMED = "confirmed"


# Report sections a finding maps into by default, aligned to the due-diligence
# report structure. Kept as plain strings so a custom template can rename them.
SECTION_ACCOUNTS = "Social Media & Online Presence"
SECTION_EMAIL = "Email Addresses"
SECTION_METADATA = "Exhibits & Digital Artifacts"
SECTION_LEADS = "Media, Social Networks & Open Sources"
SECTION_BUSINESS = "Assets & Liabilities"
SECTION_LEGAL = "Legal"

_DEFAULT_SECTION_FOR_TYPE: dict[FindingType, str] = {
    FindingType.ACCOUNT: SECTION_ACCOUNTS,
    FindingType.EMAIL: SECTION_EMAIL,
    FindingType.METADATA: SECTION_METADATA,
    FindingType.LINK: SECTION_LEADS,
    FindingType.BUSINESS: SECTION_BUSINESS,
    FindingType.LEGAL: SECTION_LEGAL,
}


def default_section_for_type(finding_type: FindingType) -> str:
    """Return the report section a finding type maps into by default."""

    return _DEFAULT_SECTION_FOR_TYPE[finding_type]


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class Finding:
    """One normalized piece of investigative signal.

    Attributes:
        type: The kind of finding, which drives its default report section.
        value: The finding itself (a URL, an email, a metadata value, a lead).
        source: A human-readable citation label for where this came from, e.g.
            ``"Maigret (github.com)"``. This is what the report cites, so it
            should stand on its own in a source list.
        source_url: An optional link to verify the finding by hand.
        status: The honest collection outcome (see FindingStatus).
        source_confidence: Certainty as reported by the collector/tool itself
            (e.g. Maigret's claimed vs confirmed distinction).
        analyst_confidence: Certainty assigned by the human during curation. The
            report cites this one, not the source confidence.
        report_section: The section this renders into. Defaults from ``type`` but
            can be overridden (for custom templates).
        included: Whether the investigator kept this finding for the report. Set
            during curation; defaults to False.
        notes: Free-text analyst notes added during curation.
        collected_at: When the finding was produced (timezone-aware UTC).
        id: Stable identifier, useful for de-duplication and UI selection.
    """

    type: FindingType
    value: str
    source: str
    source_url: str | None = None
    status: FindingStatus = FindingStatus.FOUND
    source_confidence: Confidence = Confidence.UNKNOWN
    analyst_confidence: Confidence = Confidence.UNKNOWN
    report_section: str | None = None
    included: bool = False
    notes: str = ""
    collected_at: datetime = field(default_factory=_utcnow)
    id: str = field(default_factory=lambda: uuid4().hex)

    def __post_init__(self) -> None:
        # Allow constructing from plain strings while keeping typed enums internally.
        self.type = FindingType(self.type)
        self.status = FindingStatus(self.status)
        self.source_confidence = Confidence(self.source_confidence)
        self.analyst_confidence = Confidence(self.analyst_confidence)
        if self.report_section is None:
            self.report_section = default_section_for_type(self.type)

    def to_dict(self) -> dict:
        """Serialize to a JSON-safe dict (enums to their values, datetime to ISO)."""

        return {
            "id": self.id,
            "type": self.type.value,
            "value": self.value,
            "source": self.source,
            "source_url": self.source_url,
            "status": self.status.value,
            "source_confidence": self.source_confidence.value,
            "analyst_confidence": self.analyst_confidence.value,
            "report_section": self.report_section,
            "included": self.included,
            "notes": self.notes,
            "collected_at": self.collected_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> Finding:
        """Rebuild a Finding from :meth:`to_dict` output."""

        return cls(
            id=data["id"],
            type=FindingType(data["type"]),
            value=data["value"],
            source=data["source"],
            source_url=data.get("source_url"),
            status=FindingStatus(data.get("status", FindingStatus.FOUND.value)),
            source_confidence=Confidence(
                data.get("source_confidence", Confidence.UNKNOWN.value)
            ),
            analyst_confidence=Confidence(
                data.get("analyst_confidence", Confidence.UNKNOWN.value)
            ),
            report_section=data.get("report_section"),
            included=data.get("included", False),
            notes=data.get("notes", ""),
            collected_at=datetime.fromisoformat(data["collected_at"]),
        )
