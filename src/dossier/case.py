"""The case model and its local, human-inspectable storage.

A case is one investigation into one subject. It holds the subject, a scope and
consent note (ethics is a first-class field, not a comment), and the findings
collected so far. Cases persist as a single JSON file under a gitignored
``cases/`` directory so real investigation PII never enters version control.
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

from .models import Finding
from .report.templates import DEFAULT_TEMPLATE


class SubjectType(StrEnum):
    """The kind of seed a case starts from."""

    USERNAME = "username"
    EMAIL = "email"
    NAME = "name"
    FILE = "file"


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _is_frozen() -> bool:
    """True when running from a PyInstaller (or similar) app bundle."""

    return bool(getattr(sys, "frozen", False))


def app_data_dir() -> Path:
    """Per-user data directory for the packaged app.

    A double-clicked bundle has no meaningful working directory, so persistent
    data (cases and exports) goes to the platform's user-data location instead of
    a folder next to wherever the app happened to be launched from.
    """

    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "Dossier"
    elif os.name == "nt":
        base = Path(os.environ.get("APPDATA") or Path.home()) / "Dossier"
    else:
        xdg = os.environ.get("XDG_DATA_HOME")
        base = (Path(xdg) if xdg else Path.home() / ".local" / "share") / "Dossier"
    return base


def default_cases_dir() -> Path:
    """Return the directory cases are stored in.

    Priority: the ``DOSSIER_CASES_DIR`` environment variable (useful for tests and
    for pointing at an encrypted volume); then, in a packaged app, a per-user data
    directory (see :func:`app_data_dir`); otherwise a gitignored ``cases/`` folder
    in the working directory, which is what the dev and source workflows use.
    """

    env = os.environ.get("DOSSIER_CASES_DIR")
    if env:
        return Path(env)
    if _is_frozen():
        return app_data_dir() / "cases"
    return Path("cases")


def default_exports_dir() -> Path:
    """Return the directory report exports are written to.

    Same resolution order as :func:`default_cases_dir`, overridable with the
    ``DOSSIER_EXPORTS_DIR`` environment variable.
    """

    env = os.environ.get("DOSSIER_EXPORTS_DIR")
    if env:
        return Path(env)
    if _is_frozen():
        return app_data_dir() / "exports"
    return Path("exports")


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "case"


@dataclass
class Case:
    """One investigation into one subject.

    Attributes:
        subject: The seed value (a username, email, name, or file path).
        subject_type: What kind of seed the subject is.
        title: A short human label for the case. Defaults from the subject.
        analyst: Who is running the investigation.
        authorized: Whether the analyst affirms this target is in scope and
            lawful to investigate. Passive, public data only.
        scope_note: Free text recording scope and consent ("Cover Your Analyst").
        findings: All findings collected so far (included and not).
        id: Stable identifier, also used for the on-disk filename.
        created_at / updated_at: Timezone-aware UTC timestamps.
    """

    subject: str
    subject_type: SubjectType
    title: str = ""
    analyst: str = ""
    client: str = ""  # who engaged the investigation (optional)
    authorized: bool = False
    scope_note: str = ""
    key_findings: str = ""  # analyst summary for the report front matter
    next_steps: str = ""  # analyst recommended next steps (one per line)
    template: str = DEFAULT_TEMPLATE  # which report template this case renders with
    report_html: str = ""  # the edited report document (HTML); empty = not generated
    findings: list[Finding] = field(default_factory=list)
    id: str = field(default_factory=lambda: uuid4().hex)
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        self.subject_type = SubjectType(self.subject_type)
        if not self.title:
            self.title = self.subject

    def add_finding(self, finding: Finding) -> None:
        """Append a finding and bump the modified timestamp."""

        self.findings.append(finding)
        self.touch()

    def included_findings(self) -> list[Finding]:
        """Return only the findings the investigator kept for the report."""

        return [f for f in self.findings if f.included]

    def touch(self) -> None:
        self.updated_at = _utcnow()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "subject": self.subject,
            "subject_type": self.subject_type.value,
            "title": self.title,
            "analyst": self.analyst,
            "client": self.client,
            "authorized": self.authorized,
            "scope_note": self.scope_note,
            "key_findings": self.key_findings,
            "next_steps": self.next_steps,
            "template": self.template,
            "report_html": self.report_html,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "findings": [f.to_dict() for f in self.findings],
        }

    @classmethod
    def from_dict(cls, data: dict) -> Case:
        return cls(
            id=data["id"],
            subject=data["subject"],
            subject_type=SubjectType(data["subject_type"]),
            title=data.get("title", ""),
            analyst=data.get("analyst", ""),
            client=data.get("client", ""),
            authorized=data.get("authorized", False),
            scope_note=data.get("scope_note", ""),
            key_findings=data.get("key_findings", ""),
            next_steps=data.get("next_steps", ""),
            template=data.get("template", DEFAULT_TEMPLATE),
            report_html=data.get("report_html", ""),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            findings=[Finding.from_dict(f) for f in data.get("findings", [])],
        )

    def filename(self) -> str:
        """The on-disk filename for this case (slug plus a short id for uniqueness)."""

        return f"{_slugify(self.title)}-{self.id[:8]}.json"

    def write(self, path: Path | str) -> Path:
        """Write the case to an explicit file ``path`` (creating parents)."""

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return path

    def save(self, directory: Path | str | None = None) -> Path:
        """Write the case into ``directory`` under its derived filename."""

        directory = Path(directory) if directory is not None else default_cases_dir()
        return self.write(directory / self.filename())

    @classmethod
    def load(cls, path: Path | str) -> Case:
        """Load a case from a JSON file written by :meth:`save`."""

        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data)
