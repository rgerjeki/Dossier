"""SEC EDGAR collector: US securities filings mentioning a name or company.

Uses EDGAR's full-text search (public, no key; covers filings since 2001). A hit
means the name or company appears in a public filing, which is a real
business/entity lead for the report's Assets & Liabilities section. The HTTP call
is isolated and injectable so ``normalize`` is tested offline.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from urllib.parse import quote

from ..models import Confidence, Finding, FindingStatus, FindingType
from .base import Collector, CollectorRun

Fetch = Callable[[str], tuple[int, object]]

_API = "https://efts.sec.gov/LATEST/search-index?q={q}"
_CIK = re.compile(r"CIK\s*(\d{4,10})")
_MAX = 15


def _default_fetch(url: str) -> tuple[int, object]:
    import httpx

    # SEC requires a descriptive User-Agent.
    resp = httpx.get(url, timeout=20, headers={"User-Agent": "Dossier OSINT research"})
    data: object = None
    try:
        data = resp.json()
    except ValueError:
        data = None
    return resp.status_code, data


def normalize(hits: list[dict]) -> list[Finding]:
    """Map EDGAR full-text hits to one finding per unique entity (capped)."""

    findings: list[Finding] = []
    seen: set[str] = set()
    for hit in hits:
        for name in (hit.get("_source") or {}).get("display_names") or []:
            if name in seen:
                continue
            seen.add(name)
            match = _CIK.search(name)
            url = (
                f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={match.group(1)}"
                if match
                else None
            )
            findings.append(
                Finding(
                    type=FindingType.BUSINESS,
                    value=f"SEC EDGAR filing entity: {name}",
                    source="SEC EDGAR",
                    source_url=url,
                    status=FindingStatus.FOUND,
                    source_confidence=Confidence.MEDIUM,
                )
            )
            if len(findings) >= _MAX:
                return findings
    return findings


class SECCollector(Collector):
    """Searches SEC EDGAR full-text filings for a name or company."""

    name = "SEC EDGAR"

    def __init__(self, fetch: Fetch | None = None) -> None:
        self._fetch = fetch or _default_fetch

    def collect(self, target: str) -> CollectorRun:
        query = target.strip()
        if not query:
            return CollectorRun(self.name, ok=False, message="No name or company provided.")
        try:
            status, data = self._fetch(_API.format(q=quote(f'"{query}"')))
        except Exception as exc:  # noqa: BLE001 - honest degradation
            return CollectorRun(self.name, ok=False, message=f"SEC EDGAR request failed: {exc}")

        if status != 200 or not isinstance(data, dict):
            return CollectorRun(self.name, ok=False, message=f"SEC EDGAR returned HTTP {status}.")

        hits = (data.get("hits") or {}).get("hits") or []
        findings = normalize(hits)
        return CollectorRun(
            self.name,
            findings=findings,
            ok=True,
            message=f"SEC EDGAR: {len(findings)} entity match(es) for '{query}'.",
        )
