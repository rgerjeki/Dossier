"""CourtListener collector: US court opinions matching a name or entity.

Uses the Free Law Project's CourtListener API (public, no key for anonymous use;
rate limited). A hit is a real court record and feeds the report's Legal section.
The HTTP call is isolated and injectable so ``normalize`` is tested offline.
"""

from __future__ import annotations

from collections.abc import Callable
from urllib.parse import quote

from ..models import Confidence, Finding, FindingStatus, FindingType
from .base import Collector, CollectorRun

Fetch = Callable[[str], tuple[int, object]]

_API = "https://www.courtlistener.com/api/rest/v4/search/?q={q}&type=o"
_SITE = "https://www.courtlistener.com"
_MAX = 15


def _default_fetch(url: str) -> tuple[int, object]:
    import httpx

    resp = httpx.get(
        url, timeout=20, follow_redirects=True,
        headers={"User-Agent": "Dossier-OSINT"},
    )
    data: object = None
    try:
        data = resp.json()
    except ValueError:
        data = None
    return resp.status_code, data


def normalize(results: list[dict]) -> list[Finding]:
    """Map CourtListener opinion results to legal findings (capped)."""

    findings: list[Finding] = []
    for row in results[:_MAX]:
        case = row.get("caseName") or "Unnamed case"
        court = row.get("court") or row.get("court_id") or ""
        date = row.get("dateFiled") or ""
        rel = row.get("absolute_url") or ""
        url = f"{_SITE}{rel}" if rel.startswith("/") else (rel or None)
        detail = ", ".join(x for x in (court, date) if x)
        findings.append(
            Finding(
                type=FindingType.LEGAL,
                value=f"Court opinion: {case}" + (f" ({detail})" if detail else ""),
                source="CourtListener",
                source_url=url,
                status=FindingStatus.FOUND,
                source_confidence=Confidence.MEDIUM,
            )
        )
    return findings


class CourtListenerCollector(Collector):
    """Searches CourtListener for court opinions mentioning a name or entity."""

    name = "CourtListener"

    def __init__(self, fetch: Fetch | None = None) -> None:
        self._fetch = fetch or _default_fetch

    def collect(self, target: str) -> CollectorRun:
        query = target.strip()
        if not query:
            return CollectorRun(self.name, ok=False, message="No name or entity provided.")
        try:
            status, data = self._fetch(_API.format(q=quote(f'"{query}"')))
        except Exception as exc:  # noqa: BLE001 - honest degradation
            return CollectorRun(
                self.name, ok=False, message=f"CourtListener request failed: {exc}"
            )

        if status == 429:
            return CollectorRun(
                self.name, ok=False, message="CourtListener rate limit reached. Try later."
            )
        if status != 200 or not isinstance(data, dict):
            return CollectorRun(
                self.name, ok=False, message=f"CourtListener returned HTTP {status}."
            )

        results = data.get("results") or []
        findings = normalize(results)
        total = data.get("count", len(results))
        return CollectorRun(
            self.name,
            findings=findings,
            ok=True,
            message=f"CourtListener: {len(findings)} of {total} opinion(s) for '{query}'.",
        )
