"""Username-presence collector (wraps Maigret, decision D1).

Design note: the fragile, network-bound Maigret call is isolated in
``_run_maigret`` and returns a list of plain ``SiteResult`` rows. The mapping from
those rows to normalized ``Finding`` objects lives in ``normalize``, which is a
pure function covered by tests. That way the part that carries the tool's
claimed-vs-unreachable meaning is verified without ever touching the network, and
only the thin adapter depends on Maigret's exact (and version-sensitive) API.

Absent accounts are intentionally not surfaced as findings. A username search
sweeps hundreds of sites and most come back "available"; turning every absence
into a finding would bury the real leads. We surface confirmed presences (a lead
to review) and sites we could not reach (honest degradation, never a silent
drop). Confirmed absences are counted in the run message, not listed.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..models import Confidence, Finding, FindingStatus, FindingType
from .base import Collector, CollectorRun


class MaigretNotInstalled(RuntimeError):
    """Raised by the adapter when the optional ``maigret`` package is missing."""


@dataclass
class SiteResult:
    """A single site outcome, decoupled from Maigret's own result objects.

    Attributes:
        site: The site name (for example "GitHub").
        url: The candidate profile URL, if the tool produced one.
        exists: True if the tool claims the account exists, False if it claims
            absence, None if unknown/inconclusive.
        error: True if checking this site failed (blocked, rate limited, timed
            out). Maps to ``FindingStatus.UNREACHABLE``.
    """

    site: str
    url: str | None
    exists: bool | None
    error: bool = False


def normalize(username: str, sites: list[SiteResult]) -> list[Finding]:
    """Map raw site results to findings (confirmed presences and unreachable sites)."""

    findings: list[Finding] = []
    for site in sites:
        if site.error:
            status = FindingStatus.UNREACHABLE
            source_confidence = Confidence.UNKNOWN
        elif site.exists:
            status = FindingStatus.FOUND
            # The tool asserts presence; treat that as a strong-but-not-analyst-
            # confirmed signal. The analyst confirms it during curation.
            source_confidence = Confidence.HIGH
        else:
            # Confirmed-absent or inconclusive: not a lead, do not surface.
            continue

        findings.append(
            Finding(
                type=FindingType.ACCOUNT,
                value=site.url or f"{site.site} ({username})",
                source=f"Maigret ({site.site})",
                source_url=site.url,
                status=status,
                source_confidence=source_confidence,
            )
        )
    return findings


def _summary(sites: list[SiteResult], findings: list[Finding]) -> str:
    unreachable = sum(1 for s in sites if s.error)
    found = sum(1 for f in findings if f.status is FindingStatus.FOUND)
    parts = [f"Checked {len(sites)} site(s)", f"{found} lead(s)"]
    if unreachable:
        parts.append(f"{unreachable} unreachable")
    return ", ".join(parts) + "."


class MaigretCollector(Collector):
    """Checks username presence across many sites using Maigret."""

    name = "Maigret usernames"

    def __init__(self, top_sites: int = 500, timeout: int = 30) -> None:
        self.top_sites = top_sites
        self.timeout = timeout

    def collect(self, target: str) -> CollectorRun:
        target = target.strip()
        if not target:
            return CollectorRun(self.name, ok=False, message="No username provided.")

        try:
            sites = self._run_maigret(target)
        except MaigretNotInstalled:
            return CollectorRun(
                self.name,
                ok=False,
                message=(
                    "Maigret is not installed. Enable username search with:\n"
                    '    pip install -e ".[collectors]"'
                ),
            )
        except Exception as exc:  # honest catch-all: the run failed, say so
            return CollectorRun(
                self.name, ok=False, message=f"Maigret run failed: {exc}"
            )

        findings = normalize(target, sites)
        return CollectorRun(
            self.name, findings=findings, ok=True, message=_summary(sites, findings)
        )

    def _run_maigret(self, username: str) -> list[SiteResult]:
        """Run Maigret and adapt its output to ``SiteResult`` rows.

        This is the only network-bound, Maigret-version-sensitive code in the
        collector, so it is kept thin and excluded from the offline test suite (it
        hits real sites). Verified against maigret 0.6.2: the sites DB ships at
        ``<package>/resources/data.json``; ``search`` needs a real logger; each
        result is a dict-like ``SiteResult`` whose ``status.status`` is a
        ``MaigretCheckStatus`` (CLAIMED / AVAILABLE / UNKNOWN / ILLEGAL).
        """

        import asyncio
        import logging
        import os

        try:
            import maigret
            from maigret.result import MaigretCheckStatus
        except ImportError as exc:
            raise MaigretNotInstalled from exc

        # Silence Maigret's own logging; the collector reports status itself.
        logger = logging.getLogger("dossier.maigret")
        logger.setLevel(logging.CRITICAL)

        db_path = os.path.join(
            os.path.dirname(maigret.__file__), "resources", "data.json"
        )
        db = maigret.MaigretDatabase().load_from_path(db_path)
        sites_dict = db.ranked_sites_dict(top=self.top_sites)

        raw = asyncio.run(
            maigret.search(
                username=username,
                site_dict=sites_dict,
                logger=logger,
                timeout=self.timeout,
                no_progressbar=True,
            )
        )

        rows: list[SiteResult] = []
        for site_name, data in raw.items():
            status = getattr(data.get("status"), "status", None)
            rows.append(
                SiteResult(
                    site=site_name,
                    url=data.get("url_user"),
                    exists=(status == MaigretCheckStatus.CLAIMED),
                    # UNKNOWN (or a missing status) means the check could not be
                    # resolved: blocked, rate limited, or errored. AVAILABLE and
                    # ILLEGAL are honest absences, not failures.
                    error=(status is None or status == MaigretCheckStatus.UNKNOWN),
                )
            )
        return rows
