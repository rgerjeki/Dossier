"""Search-kit collector: guided pivot links for sources Dossier does not scrape.

Most valuable OSINT sources (social platforms, people/address search, reverse
image search, breach checkers, public records) are behind logins or anti-bot
controls, so they return real data only to a real browser. Rather than fragile
scrapers, this builds ready-to-open URLs the investigator opens and reviews by
hand. That is how professional OSINT actually works, and it is reliable.

The links generated depend on what the target looks like: a handle (username), a
full name, an email, an image URL (for reverse image search), or a domain. Pure
and offline: it builds URLs from templates, it does not fetch them.
"""

from __future__ import annotations

from urllib.parse import quote

from ..models import Confidence, Finding, FindingStatus, FindingType
from .base import Collector, CollectorRun

# Target kinds. A finding template applies to one or more of these.
_HANDLE = "handle"  # a single-token username
_NAME = "name"  # a person's name (has a space)
_EMAIL = "email"
_URL = "url"  # an image URL, for reverse image search
_DOMAIN = "domain"
_ALL = (_HANDLE, _NAME, _EMAIL, _URL, _DOMAIN)

# (category, label, url template, applicable kinds). Each source is tagged with the
# selector types it actually supports, so a target never gets a link that is
# invalid for it (e.g. Intelligence X only takes email/domain/IP, never a name).
# Templates use: {q} url-encoded query, {u} path-safe token, {slug} name slug,
# {d} raw domain.
_LINKS: list[tuple[str, str, str, tuple[str, ...]]] = [
    # General web search accepts any string.
    ("Web search", "Google (exact)", 'https://www.google.com/search?q="{q}"', _ALL),
    ("Web search", "Google", "https://www.google.com/search?q={q}", _ALL),
    ("Web search", "Bing", "https://www.bing.com/search?q={q}", _ALL),
    ("Web search", "DuckDuckGo", "https://duckduckgo.com/?q={q}", _ALL),
    ("Web search", "Google News", "https://www.google.com/search?q={q}&tbm=nws", _ALL),
    # Social profiles: a handle only (a name would make a nonsense URL).
    ("Social", "Instagram", "https://www.instagram.com/{u}/", (_HANDLE,)),
    ("Social", "X (Twitter)", "https://x.com/{u}", (_HANDLE,)),
    ("Social", "Facebook", "https://www.facebook.com/{u}", (_HANDLE,)),
    ("Social", "TikTok", "https://www.tiktok.com/@{u}", (_HANDLE,)),
    ("Social", "Reddit", "https://www.reddit.com/user/{u}", (_HANDLE,)),
    ("Social", "YouTube", "https://www.youtube.com/@{u}", (_HANDLE,)),
    ("Social", "GitHub", "https://github.com/{u}", (_HANDLE,)),
    # Social keyword search: a handle or a name.
    ("Social", "LinkedIn (search)",
     "https://www.linkedin.com/search/results/all/?keywords={q}", (_HANDLE, _NAME)),
    ("Social", "Facebook (people search)",
     "https://www.facebook.com/search/people/?q={q}", (_HANDLE, _NAME)),
    # People / address search: needs a real name (first + last), not a username.
    ("People search", "TruePeopleSearch",
     "https://www.truepeoplesearch.com/results?name={q}", (_NAME,)),
    ("People search", "FastPeopleSearch",
     "https://www.fastpeoplesearch.com/name/{slug}", (_NAME,)),
    ("People search", "ThatsThem", "https://thatsthem.com/name/{slug}", (_NAME,)),
    ("People search", "WhitePages", "https://www.whitepages.com/name/{slug}", (_NAME,)),
    ("People search", "Spokeo", "https://www.spokeo.com/{slug}", (_NAME,)),
    # Breach / leak checkers, each with its real selector support.
    ("Breach & leak", "Have I Been Pwned", "https://haveibeenpwned.com/", (_EMAIL,)),
    ("Breach & leak", "DeHashed", "https://dehashed.com/search?query={q}",
     (_HANDLE, _NAME, _EMAIL, _DOMAIN)),
    ("Breach & leak", "Intelligence X", "https://intelx.io/?s={q}", (_EMAIL, _DOMAIN)),
    # Business, entity, and legal records: a name or a (single-token) company.
    ("Business & legal", "SEC EDGAR",
     "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company={q}&count=40",
     (_HANDLE, _NAME)),
    ("Business & legal", "OpenCorporates",
     "https://opencorporates.com/companies?q={q}", (_HANDLE, _NAME)),
    ("Business & legal", "CourtListener", "https://www.courtlistener.com/?q={q}", (_HANDLE, _NAME)),
    ("Business & legal", "Google Scholar",
     "https://scholar.google.com/scholar?q={q}", (_HANDLE, _NAME)),
    # Reverse image search: needs an image URL.
    ("Reverse image", "Google Lens", "https://lens.google.com/uploadbyurl?url={q}", (_URL,)),
    ("Reverse image", "Yandex", "https://yandex.com/images/search?rpt=imageview&url={q}", (_URL,)),
    ("Reverse image", "TinEye", "https://tineye.com/search?url={q}", (_URL,)),
    ("Reverse image", "Bing Visual",
     "https://www.bing.com/images/search?view=detailv2&iss=sbi&q=imgurl:{q}", (_URL,)),
    # Domain / infrastructure.
    ("Domain", "crt.sh (subdomains)", "https://crt.sh/?q={d}", (_DOMAIN,)),
    ("Domain", "Wayback Machine", "https://web.archive.org/web/*/{d}", (_DOMAIN,)),
    ("Domain", "WHOIS", "https://www.whois.com/whois/{d}", (_DOMAIN,)),
    ("Domain", "DNS (MXToolbox)",
     "https://mxtoolbox.com/SuperTool.aspx?action=mx:{d}&run=toolpage", (_DOMAIN,)),
]


def _kind(target: str) -> str:
    t = target.strip()
    if t.startswith(("http://", "https://")):
        return _URL
    if "@" in t:
        return _EMAIL
    if "." in t and " " not in t and "/" not in t:
        return _DOMAIN
    if " " in t:
        return _NAME
    return _HANDLE


def generate_links(target: str) -> list[Finding]:
    """Build the guided pivot-link findings appropriate for the target."""

    target = target.strip()
    kind = _kind(target)
    subs = {
        "q": quote(target),
        "u": quote(target, safe=""),
        "slug": target.lower().replace(" ", "-"),
        "d": target,
    }
    findings: list[Finding] = []
    for category, label, template, kinds in _LINKS:
        if kind not in kinds:
            continue
        url = template.format(**subs)
        findings.append(
            Finding(
                type=FindingType.LINK,
                value=f"{label}: {url}",
                source=f"Search-kit ({category}: {label})",
                source_url=url,
                status=FindingStatus.FOUND,
                source_confidence=Confidence.UNKNOWN,
                notes=f"Guided link ({category}); open and review by hand.",
            )
        )
    return findings


class SearchKitCollector(Collector):
    """Generates guided pivot links for a target to review by hand."""

    name = "Search-kit"

    def collect(self, target: str) -> CollectorRun:
        target = target.strip()
        if not target:
            return CollectorRun(self.name, ok=False, message="No target provided.")
        findings = generate_links(target)
        kind = _kind(target)
        return CollectorRun(
            self.name,
            findings=findings,
            ok=True,
            message=f"Generated {len(findings)} guided pivot link(s) for a {kind}.",
        )
