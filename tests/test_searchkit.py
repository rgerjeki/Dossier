"""Tests for the search-kit collector. Pure and offline (no URLs are fetched)."""

from __future__ import annotations

from dossier.collectors.base import Collector
from dossier.collectors.searchkit import SearchKitCollector, generate_links
from dossier.models import Confidence, FindingStatus, FindingType


def _urls(target: str) -> list[str]:
    return [f.source_url for f in generate_links(target)]


def test_all_links_are_link_findings() -> None:
    for f in generate_links("rgerjeki"):
        assert f.type is FindingType.LINK
        assert f.status is FindingStatus.FOUND
        assert f.source_confidence is Confidence.UNKNOWN
        assert f.source_url


def test_handle_gets_profiles_not_people_search() -> None:
    urls = _urls("rgerjeki")
    assert any("instagram.com/rgerjeki" in u for u in urls)  # profile
    assert any("github.com/rgerjeki" in u for u in urls)
    assert any("google.com/search" in u for u in urls)
    # People/address search needs a real name, not a username.
    assert not any("truepeoplesearch.com" in u for u in urls)


def test_full_name_gets_people_search_not_invalid_selectors() -> None:
    urls = _urls("John Smith")
    # No nonsense profile URL like instagram.com/John%20Smith
    assert not any("instagram.com/John" in u for u in urls)
    # People/address + keyword search apply
    assert any("fastpeoplesearch.com/name/john-smith" in u for u in urls)
    assert any("linkedin.com/search" in u for u in urls)
    # The reported bug: Intelligence X only takes selectors, never a name.
    assert not any("intelx.io" in u for u in urls)
    # HIBP checks emails, not names.
    assert not any("haveibeenpwned.com" in u for u in urls)


def test_image_url_gets_reverse_image_search() -> None:
    urls = _urls("https://example.com/photo.jpg")
    assert any("tineye.com/search?url=" in u for u in urls)
    assert any("yandex.com/images/search" in u for u in urls)
    assert any("lens.google.com" in u for u in urls)
    # reverse-image only, not social profiles
    assert not any("instagram.com" in u for u in urls)


def test_domain_gets_infrastructure_and_valid_breach() -> None:
    urls = _urls("example.com")
    assert any("crt.sh/?q=example.com" in u for u in urls)
    assert any("web.archive.org/web/" in u for u in urls)
    assert any("whois.com/whois/example.com" in u for u in urls)
    assert any("intelx.io" in u for u in urls)  # IntelX does take a domain
    assert not any("instagram.com" in u for u in urls)


def test_email_gets_valid_breach_not_profiles_or_intelx_name_case() -> None:
    urls = _urls("jane@example.com")
    assert any("haveibeenpwned.com" in u for u in urls)  # HIBP takes an email
    assert any("intelx.io" in u for u in urls)  # IntelX takes an email
    assert any("google.com/search" in u for u in urls)
    assert not any("instagram.com/jane" in u for u in urls)  # no profile guess
    assert not any("truepeoplesearch.com" in u for u in urls)  # not a name


def test_collect_reports_kind() -> None:
    run = SearchKitCollector().collect("rgerjeki")
    assert run.ok is True
    assert "handle" in run.message
    assert len(run.findings) == len(generate_links("rgerjeki"))


def test_collect_rejects_empty() -> None:
    assert SearchKitCollector().collect("   ").ok is False


def test_is_a_collector() -> None:
    assert isinstance(SearchKitCollector(), Collector)
