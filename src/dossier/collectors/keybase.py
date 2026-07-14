"""Keybase collector: a username's cryptographically proven accounts elsewhere.

Keybase lets a user prove they control accounts on other services (Twitter/X,
GitHub, Reddit, Hacker News, websites, DNS). Those proofs are exactly the identity
correlation OSINT wants: one handle maps to verified handles on other platforms.
Real data, no API key. Coverage is limited to people who set up Keybase (the
service is largely dormant since 2020), so a miss is honestly reported.

The HTTP call is isolated and injectable so ``normalize`` is tested offline.
"""

from __future__ import annotations

from collections.abc import Callable
from urllib.parse import quote

from ..models import Confidence, Finding, FindingStatus, FindingType
from .base import Collector, CollectorRun

Fetch = Callable[[str], tuple[int, object]]

_API = "https://keybase.io/_/api/1.0/user/lookup.json?usernames={u}&fields=proofs_summary"
_WEB_PROOFS = {"dns", "generic_web_site", "web", "https", "http"}


def _default_fetch(url: str) -> tuple[int, object]:
    import httpx

    resp = httpx.get(
        url, timeout=15, follow_redirects=True,
        headers={"User-Agent": "Dossier-OSINT"},
    )
    data: object = None
    try:
        data = resp.json()
    except ValueError:
        data = None
    return resp.status_code, data


def normalize(username: str, proofs: list[dict]) -> list[Finding]:
    """Map Keybase proof entries to findings (verified accounts and sites)."""

    findings: list[Finding] = []
    for proof in proofs:
        ptype = (proof.get("proof_type") or "").lower()
        nametag = proof.get("nametag") or ""
        url = proof.get("service_url") or None
        if ptype in _WEB_PROOFS:
            findings.append(
                Finding(
                    type=FindingType.LINK,
                    value=f"Keybase-verified website: {nametag or url}",
                    source=f"Keybase ({username})",
                    source_url=url,
                    status=FindingStatus.FOUND,
                    source_confidence=Confidence.CONFIRMED,
                )
            )
        else:
            findings.append(
                Finding(
                    type=FindingType.ACCOUNT,
                    value=f"Keybase-verified {ptype}: {nametag}",
                    source=f"Keybase ({username})",
                    source_url=url,
                    status=FindingStatus.FOUND,
                    source_confidence=Confidence.CONFIRMED,
                )
            )
    return findings


class KeybaseCollector(Collector):
    """Looks up a Keybase user's proven accounts on other platforms."""

    name = "Keybase"

    def __init__(self, fetch: Fetch | None = None) -> None:
        self._fetch = fetch or _default_fetch

    def collect(self, target: str) -> CollectorRun:
        username = target.strip().lstrip("@")
        if not username:
            return CollectorRun(self.name, ok=False, message="No username provided.")
        try:
            status, data = self._fetch(_API.format(u=quote(username, safe="")))
        except Exception as exc:  # noqa: BLE001 - honest degradation
            return CollectorRun(self.name, ok=False, message=f"Keybase request failed: {exc}")

        if status != 200 or not isinstance(data, dict):
            return CollectorRun(self.name, ok=False, message=f"Keybase returned HTTP {status}.")

        them = data.get("them") or []
        if not them or not isinstance(them[0], dict):
            return CollectorRun(self.name, ok=True, message=f"No Keybase user '{username}'.")

        proofs = (them[0].get("proofs_summary") or {}).get("all") or []
        findings = normalize(username, proofs)
        return CollectorRun(
            self.name,
            findings=findings,
            ok=True,
            message=f"Keybase user '{username}': {len(findings)} verified account(s).",
        )
