"""Email collector: Gravatar (built here) plus optional holehe account-existence.

Gravatar is simple and reliable, so we build it ourselves: hash the email, check
whether an avatar and a public profile exist, and turn the profile into findings.
holehe (account-existence across services) is wrapped when installed; it is
brittle upstream, so its failures degrade to UNREACHABLE rather than dropping.

The Gravatar HTTP call is injectable (``fetch``) so the collector is fully
testable without the network.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable

from ..models import Confidence, Finding, FindingStatus, FindingType
from .base import Collector, CollectorRun

# fetch(url) -> (status_code, parsed_json_or_None). Raises on a transport error.
Fetch = Callable[[str], tuple[int, object]]

_AVATAR_URL = "https://www.gravatar.com/avatar/{h}?d=404"
_PROFILE_URL = "https://www.gravatar.com/{h}.json"


def gravatar_hash(email: str) -> str:
    """Gravatar's identifier: SHA-256 of the trimmed, lowercased email."""

    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()


def _default_fetch(url: str) -> tuple[int, object]:
    import httpx

    resp = httpx.get(url, timeout=15, follow_redirects=True)
    data: object = None
    if resp.status_code == 200 and "json" in resp.headers.get("content-type", ""):
        try:
            data = resp.json()
        except ValueError:
            data = None
    return resp.status_code, data


def gravatar_findings(email: str, fetch: Fetch) -> list[Finding]:
    """Build Gravatar findings for an email using the given fetch callable."""

    h = gravatar_hash(email)
    findings: list[Finding] = []

    try:
        avatar_status, _ = fetch(_AVATAR_URL.format(h=h))
    except Exception:
        return [
            Finding(
                type=FindingType.EMAIL,
                value=f"Gravatar lookup for {email}",
                source="Gravatar",
                status=FindingStatus.UNREACHABLE,
            )
        ]

    if avatar_status == 200:
        findings.append(
            Finding(
                type=FindingType.EMAIL,
                value=f"Gravatar avatar exists for {email}",
                source="Gravatar",
                source_url=f"https://www.gravatar.com/avatar/{h}",
                status=FindingStatus.FOUND,
                source_confidence=Confidence.HIGH,
            )
        )
    else:
        # No avatar: a confirmed absence, recorded but not a lead.
        findings.append(
            Finding(
                type=FindingType.EMAIL,
                value=f"No Gravatar avatar for {email}",
                source="Gravatar",
                status=FindingStatus.NOT_FOUND,
            )
        )

    try:
        profile_status, profile = fetch(_PROFILE_URL.format(h=h))
    except Exception:
        profile_status, profile = None, None

    if profile_status == 200 and isinstance(profile, dict):
        entries = profile.get("entry") or []
        if entries:
            findings.extend(_profile_findings(email, h, entries[0]))

    return findings


def _profile_findings(email: str, h: str, entry: dict) -> list[Finding]:
    profile_url = f"https://www.gravatar.com/{h}"
    out: list[Finding] = []
    display = entry.get("displayName") or entry.get("preferredUsername")
    if display:
        out.append(
            Finding(
                type=FindingType.EMAIL,
                value=f"Gravatar display name: {display}",
                source="Gravatar profile",
                source_url=profile_url,
                status=FindingStatus.FOUND,
                source_confidence=Confidence.MEDIUM,
            )
        )
    for account in entry.get("accounts") or []:
        label = account.get("shortname") or account.get("domain") or "account"
        url = account.get("url")
        out.append(
            Finding(
                type=FindingType.ACCOUNT,
                value=f"Linked {label}: {url}",
                source="Gravatar profile",
                source_url=url,
                status=FindingStatus.FOUND,
                source_confidence=Confidence.MEDIUM,
            )
        )
    return out


class EmailCollector(Collector):
    """Looks up an email via Gravatar, and via holehe when it is installed."""

    name = "Email (Gravatar + holehe)"

    def __init__(self, fetch: Fetch | None = None, use_holehe: bool = True) -> None:
        self._fetch = fetch or _default_fetch
        self._use_holehe = use_holehe

    def collect(self, target: str) -> CollectorRun:
        target = target.strip()
        if "@" not in target:
            return CollectorRun(
                self.name, ok=False, message="Enter a valid email address."
            )

        findings = gravatar_findings(target, self._fetch)
        holehe_note = ""
        if self._use_holehe:
            try:
                findings.extend(self._run_holehe(target))
            except _HoleheUnavailable:
                holehe_note = " holehe not installed (Gravatar only)."
            except Exception as exc:  # noqa: BLE001 - honest degradation
                holehe_note = f" holehe failed: {exc}."

        found = sum(1 for f in findings if f.status is FindingStatus.FOUND)
        message = f"{len(findings)} result(s), {found} confirmed.{holehe_note}"
        return CollectorRun(self.name, findings=findings, ok=True, message=message)

    def _run_holehe(self, email: str) -> list[Finding]:
        """Run holehe and adapt its output. Isolated network-bound adapter.

        Verified against holehe's live API: each module in ``holehe.modules``
        exposes an async site function named after the module's last path segment
        with signature ``(email, client, out)`` that appends a result dict (keys
        ``name``, ``exists``, ``rateLimit``) to ``out``. Runs all modules; one
        broken module never stops the sweep. Excluded from the offline tests.
        """

        import asyncio
        import inspect

        try:
            import httpx as _httpx
            from holehe.core import import_submodules
        except ImportError as exc:
            raise _HoleheUnavailable from exc

        modules = import_submodules("holehe.modules")
        site_funcs = []
        for modname, mod in modules.items():
            fn = getattr(mod, modname.split(".")[-1], None)
            if (
                fn is not None
                and inspect.iscoroutinefunction(fn)
                and list(inspect.signature(fn).parameters) == ["email", "client", "out"]
            ):
                site_funcs.append(fn)

        async def _run() -> list[dict]:
            out: list[dict] = []
            async with _httpx.AsyncClient() as client:
                for site in site_funcs:
                    try:
                        await site(email, client, out)
                    except Exception:  # noqa: BLE001 - one broken module must not stop the run
                        continue
            return out

        return _holehe_findings(email, asyncio.run(_run()))


class _HoleheUnavailable(RuntimeError):
    pass


def _holehe_findings(email: str, raw: list[dict]) -> list[Finding]:
    """Map holehe's per-site dicts to findings (confirmed existence only)."""

    findings: list[Finding] = []
    for row in raw:
        if row.get("exists") is True:
            name = row.get("name", "service")
            findings.append(
                Finding(
                    type=FindingType.ACCOUNT,
                    value=f"Account exists at {name} for {email}",
                    source=f"holehe ({name})",
                    status=FindingStatus.FOUND,
                    source_confidence=Confidence.MEDIUM,
                )
            )
        elif row.get("rateLimit") is True or row.get("exists") is None:
            name = row.get("name", "service")
            findings.append(
                Finding(
                    type=FindingType.ACCOUNT,
                    value=f"Could not check {name} for {email}",
                    source=f"holehe ({name})",
                    status=FindingStatus.UNREACHABLE,
                )
            )
    return findings
