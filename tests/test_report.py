"""Tests for the report render engine (full due-diligence skeleton). No Qt."""

from __future__ import annotations

from dossier.case import Case, SubjectType
from dossier.models import Confidence, Finding, FindingType
from dossier.report import render


def _case() -> Case:
    case = Case(
        subject="rgerjeki",
        subject_type=SubjectType.USERNAME,
        analyst="Reese",
        authorized=True,
        scope_note="Safe target (self).",
    )
    case.add_finding(
        Finding(
            type=FindingType.ACCOUNT,
            value="https://github.com/rgerjeki",
            source="Maigret (GitHub)",
            source_url="https://github.com/rgerjeki",
            included=True,
            analyst_confidence=Confidence.HIGH,
            notes="primary account",
        )
    )
    # same source as above -> should share one citation number
    case.add_finding(
        Finding(
            type=FindingType.ACCOUNT,
            value="https://github.com/rgerjeki?tab=repos",
            source="Maigret (GitHub)",
            source_url="https://github.com/rgerjeki",
            included=True,
        )
    )
    case.add_finding(
        Finding(type=FindingType.EMAIL, value="has Gravatar", source="Gravatar", included=True)
    )
    case.add_finding(
        Finding(type=FindingType.ACCOUNT, value="EXCLUDED", source="Maigret (Foo)")
    )
    return case


def test_outline_is_the_full_due_diligence_skeleton() -> None:
    ctx = render.build_report_context(_case())
    titles = [s.title for s in ctx.sections]
    for expected in (
        "Personal & Residence",
        "Email Addresses",
        "Social Media & Online Presence",
        "Assets & Liabilities",
        "Professional Development",
        "Legal",
        "Media, Social Networks & Open Sources",
        "Exhibits & Digital Artifacts",
    ):
        assert expected in titles


def test_findings_placed_by_type_only_when_included() -> None:
    ctx = render.build_report_context(_case())
    by_title = {s.title: s for s in ctx.sections}
    assert len(by_title["Social Media & Online Presence"].findings) == 2  # github x2
    assert len(by_title["Email Addresses"].findings) == 1
    values = [f.value for s in ctx.sections for f in s.findings]
    assert "EXCLUDED" not in values


def test_manual_sections_are_scaffolded() -> None:
    ctx = render.build_report_context(_case())
    manual = next(s for s in ctx.sections if s.title == "Professional Development")
    assert manual.is_manual is True
    assert manual.note


def test_partly_automatable_sections_collect_and_keep_a_note() -> None:
    # Legal/Assets are now collected (SEC, CourtListener) but keep manual guidance.
    ctx = render.build_report_context(_case())
    legal = next(s for s in ctx.sections if s.title == "Legal")
    assert legal.is_manual is False
    assert legal.note  # still tells the analyst what to complete by hand


def test_citations_deduplicate_by_source() -> None:
    ctx = render.build_report_context(_case())
    assert [c.number for c in ctx.citations] == [1, 2]
    github = [f for s in ctx.sections for f in s.findings if "github.com" in f.value]
    assert {ctx.citation_number(f) for f in github} == {1}


def test_default_front_matter_makes_no_claim() -> None:
    ctx = render.build_report_context(_case())
    # The default must be a neutral prompt, not a substantive claim the tool
    # cannot support (e.g. "no derogatory information was located").
    assert "Summarize the key findings" in ctx.key_findings
    assert "derogatory" not in ctx.key_findings.lower()
    assert len(ctx.next_steps) >= 1
    assert "Maigret" in ctx.methodology


def test_custom_front_matter_overrides_defaults() -> None:
    case = _case()
    case.key_findings = "Subject is a public figure with an extensive footprint."
    case.next_steps = "- Verify GitHub\n- Check breach data"
    ctx = render.build_report_context(case)
    assert ctx.key_findings == "Subject is a public figure with an extensive footprint."
    assert ctx.next_steps == ["Verify GitHub", "Check breach data"]


def test_render_html_has_front_matter_and_sections() -> None:
    html = render.render_html(_case())
    assert "PRIVATE AND CONFIDENTIAL" in html
    assert "Key Findings" in html
    assert "Search Methodology" in html
    assert "Social Media &amp; Online Presence" in html
    assert "To complete:" in html  # a manual scaffold section
    assert "Sources" in html
    assert "EXCLUDED" not in html


def test_render_html_empty_case_still_shows_skeleton() -> None:
    case = Case(subject="x", subject_type=SubjectType.USERNAME)
    case.add_finding(Finding(type=FindingType.ACCOUNT, value="v", source="s"))  # not included
    html = render.render_html(case)
    assert "No results were located through automated collection." in html
    assert "Legal" in html


def test_headings_are_semantic() -> None:
    # Sections use <h2> so headings survive into the Word (HTML-to-docx) export.
    html = render.render_html(_case())
    assert "<h2" in html
    assert "<h2" in html.split("Legal")[0]
