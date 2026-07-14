"""GitHub collector: a username's public profile via the GitHub REST API.

Real data, no API key (the public endpoint allows unauthenticated requests, rate
limited to 60/hour). The HTTP call is isolated in ``_default_fetch`` and injectable
so ``normalize`` is tested without the network.
"""

from __future__ import annotations

from collections.abc import Callable
from urllib.parse import quote

from ..models import Confidence, Finding, FindingStatus, FindingType
from .base import Collector, CollectorRun

# fetch(url) -> (status_code, parsed_json_or_None). Raises on a transport error.
Fetch = Callable[[str], tuple[int, object]]

_API = "https://api.github.com/users/{u}"


def _default_fetch(url: str) -> tuple[int, object]:
    import httpx

    resp = httpx.get(
        url,
        timeout=15,
        follow_redirects=True,
        headers={
            "User-Agent": "Dossier-OSINT",
            "Accept": "application/vnd.github+json",
        },
    )
    data: object = None
    if "json" in resp.headers.get("content-type", ""):
        try:
            data = resp.json()
        except ValueError:
            data = None
    return resp.status_code, data


def normalize(profile: dict) -> list[Finding]:
    """Map a GitHub user profile to findings."""

    findings: list[Finding] = []
    html_url = profile.get("html_url") or ""

    detail_bits = []
    for label, key in (
        ("name", "name"),
        ("company", "company"),
        ("location", "location"),
        ("bio", "bio"),
        ("public repos", "public_repos"),
        ("followers", "followers"),
        ("joined", "created_at"),
    ):
        value = profile.get(key)
        if value not in (None, ""):
            detail_bits.append(f"{label}: {value}")

    findings.append(
        Finding(
            type=FindingType.ACCOUNT,
            value=f"GitHub profile: {html_url}",
            source="GitHub",
            source_url=html_url or None,
            status=FindingStatus.FOUND,
            source_confidence=Confidence.HIGH,
            notes="; ".join(detail_bits),
        )
    )

    email = profile.get("email")
    if email:
        findings.append(
            Finding(
                type=FindingType.EMAIL,
                value=f"Public GitHub email: {email}",
                source="GitHub",
                source_url=html_url or None,
                status=FindingStatus.FOUND,
                source_confidence=Confidence.HIGH,
            )
        )

    blog = profile.get("blog")
    if blog:
        url = blog if blog.startswith("http") else f"https://{blog}"
        findings.append(
            Finding(
                type=FindingType.LINK,
                value=f"Website (from GitHub): {url}",
                source="GitHub profile",
                source_url=url,
                status=FindingStatus.FOUND,
                source_confidence=Confidence.MEDIUM,
            )
        )

    twitter = profile.get("twitter_username")
    if twitter:
        url = f"https://x.com/{twitter}"
        findings.append(
            Finding(
                type=FindingType.ACCOUNT,
                value=f"X (Twitter) from GitHub: {url}",
                source="GitHub profile",
                source_url=url,
                status=FindingStatus.FOUND,
                source_confidence=Confidence.MEDIUM,
            )
        )

    return findings


class GitHubCollector(Collector):
    """Fetches a username's public GitHub profile."""

    name = "GitHub"

    def __init__(self, fetch: Fetch | None = None) -> None:
        self._fetch = fetch or _default_fetch

    def collect(self, target: str) -> CollectorRun:
        username = target.strip().lstrip("@")
        if not username:
            return CollectorRun(self.name, ok=False, message="No username provided.")
        try:
            status, data = self._fetch(_API.format(u=quote(username, safe="")))
        except Exception as exc:  # noqa: BLE001 - honest degradation
            return CollectorRun(self.name, ok=False, message=f"GitHub request failed: {exc}")

        if status == 404:
            return CollectorRun(self.name, ok=True, message=f"No GitHub user '{username}'.")
        if status == 403:
            return CollectorRun(
                self.name,
                ok=False,
                message="GitHub rate limit reached (60/hour unauthenticated). Try later.",
            )
        if status != 200 or not isinstance(data, dict):
            return CollectorRun(self.name, ok=False, message=f"GitHub returned HTTP {status}.")

        findings = normalize(data)
        return CollectorRun(
            self.name,
            findings=findings,
            ok=True,
            message=f"GitHub profile for {username}: {len(findings)} finding(s).",
        )
