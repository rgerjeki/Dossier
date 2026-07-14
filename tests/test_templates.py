"""Tests for the report template registry and per-template rendering. No Qt."""

from __future__ import annotations

from dossier.case import Case, SubjectType
from dossier.models import Finding, FindingType
from dossier.report import render
from dossier.report.templates import DEFAULT_TEMPLATE, TEMPLATES, get_template


def _entity_case(template: str) -> Case:
    case = Case(subject="Tesla Inc", subject_type=SubjectType.NAME, template=template)
    case.add_finding(
        Finding(type=FindingType.BUSINESS, value="Tesla Inc (CIK 1318605)", source="SEC EDGAR",
                source_url="https://www.sec.gov/cgi-bin/browse-edgar", included=True)
    )
    case.add_finding(
        Finding(type=FindingType.LEGAL, value="SEC v. Musk", source="CourtListener",
                source_url="https://www.courtlistener.com/x", included=True)
    )
    return case


def test_registry_has_the_four_templates() -> None:
    assert set(TEMPLATES) == {"due_diligence", "tracelabs", "kyb", "profile"}
    assert DEFAULT_TEMPLATE == "due_diligence"


def test_unknown_template_falls_back_to_default() -> None:
    assert get_template("does-not-exist").key == DEFAULT_TEMPLATE


def test_default_case_uses_full_background() -> None:
    case = Case(subject="x", subject_type=SubjectType.USERNAME)
    assert case.template == "due_diligence"
    html = render.render_html(case)
    assert "FULL BACKGROUND INVESTIGATION" in html
    assert "Subject: x" in html


def test_kyb_makes_business_and_legal_first_class() -> None:
    ctx = render.build_report_context(_entity_case("kyb"))
    by_title = {s.title: s for s in ctx.sections}
    # BUSINESS/LEGAL are dedicated collected sections here, not person subsections.
    assert by_title["Registrations & Filings"].findings  # SEC BUSINESS finding placed
    assert by_title["Litigation & Legal"].findings  # CourtListener LEGAL finding placed
    assert "Assets & Liabilities" not in by_title  # that is the person template's title


def test_kyb_reflects_verified_aml_structure() -> None:
    ctx = render.build_report_context(_entity_case("kyb"))
    by_title = {s.title: s for s in ctx.sections}
    # UBO section names the 25% threshold (FATF R24/R25; FinCEN CDD; EU AMLD).
    ubo = by_title["Ownership & Beneficial Owners"]
    assert "25%" in ubo.note
    # Screening covers sanctions AND politically exposed persons.
    screening = by_title["Sanctions, PEP & Watchlist Screening"]
    assert "PEP" in screening.note or "politically exposed" in screening.note.lower()
    # Risk assessment is a first-class section (KYB phase 3), not an afterthought.
    assert "Risk Assessment" in by_title
    # The 25% UBO threshold is also reinforced in the recommended next steps.
    assert any("25%" in s for s in ctx.next_steps)


def test_kyb_front_matter_and_methodology() -> None:
    ctx = render.build_report_context(_entity_case("kyb"))
    html = render.render_html(ctx.case)
    assert "CORPORATE DUE DILIGENCE" in html
    assert "Entity: Tesla Inc" in html  # entity, not "Subject"
    # KYB methodology names the entity collectors, not the person ones.
    assert "SEC EDGAR" in ctx.methodology and "CourtListener" in ctx.methodology
    assert "Maigret" not in ctx.methodology
    assert "Tesla Inc" in ctx.methodology  # {subject} was substituted


def test_tracelabs_mirrors_the_scoring_categories() -> None:
    case = Case(subject="jane", subject_type=SubjectType.NAME, template="tracelabs")
    ctx = render.build_report_context(case)
    titles = [s.title for s in ctx.sections]
    # Each of the eight TraceLabs flag categories has a home section (verified
    # against the TraceLabs flag-categories guide).
    for expected in (
        "Basic Subject Information",
        "Advanced Subject Information",
        "Friends, Family & Associates",
        "Employment",
        "Day Last Seen",
        "Advancing the Timeline",
        "Location Intelligence",
        "Dark Web & Breach Exposure",
    ):
        assert expected in titles, expected
    html = render.render_html(case)
    assert "MISSING PERSON OSINT REPORT" in html


def test_tracelabs_surfaces_the_real_conduct_rules() -> None:
    case = Case(subject="jane", subject_type=SubjectType.NAME, template="tracelabs")
    ctx = render.build_report_context(case)
    steps = " ".join(ctx.next_steps).lower()
    # Passive/zero-touch and the no-contact-equals-disqualification rule.
    assert "zero touch" in steps or "passive" in steps
    assert "disqualif" in steps
    # Passive-recon conduct is also stated in the methodology.
    assert "passive" in ctx.methodology.lower()


def test_profile_is_collected_only_no_scaffolds() -> None:
    case = Case(subject="dave", subject_type=SubjectType.USERNAME, template="profile")
    ctx = render.build_report_context(case)
    assert [s.title for s in ctx.sections] == [
        "Online Accounts", "Email", "Leads & Open Sources", "Metadata",
    ]
    assert all(not s.is_manual for s in ctx.sections)  # no manual scaffold sections
    html = render.render_html(case)
    assert "SUBJECT PROFILE" in html
    assert "To complete:" not in html  # nothing to hand-complete in the one-pager


def test_case_persists_template_round_trip() -> None:
    case = Case(subject="Acme LLC", subject_type=SubjectType.NAME, template="kyb")
    restored = Case.from_dict(case.to_dict())
    assert restored.template == "kyb"
    # A legacy case file without the field defaults to the full background report.
    legacy = {k: v for k, v in case.to_dict().items() if k != "template"}
    assert Case.from_dict(legacy).template == DEFAULT_TEMPLATE
