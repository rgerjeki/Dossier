"""Findings to a cited investigation report (HTML, the single source of truth).

The report has shared front matter (Key Findings, Recommended Next Steps, Search
Methodology) followed by a section outline chosen from a named template (see
``templates.py``): a full person background (the CYBV 354 default), a TraceLabs
missing-person report, a company/entity (KYB) due diligence, or a one-page
profile. Some sections are auto-filled from findings by type (emails, social
presence, media/open-source links, metadata exhibits); the rest are analyst
scaffolding, because that data needs sources Dossier does not touch. Nothing is
faked: a collected section with no findings says so, and a scaffold section states
plainly that it must be completed by hand.

``render_html`` produces the report document. The UI loads it into an editable
document that the investigator can freely edit; the PDF and Word exports both come
from that edited document (see ``dossier.ui.export``). This module is Qt-free.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from datetime import UTC, datetime

from ..case import Case
from ..models import Finding
from .templates import ReportTemplate, SectionSpec, get_template

# Re-exported for callers that still import the person outline from here.
DUE_DILIGENCE_OUTLINE: list[SectionSpec] = get_template("due_diligence").outline

# Report typography (reference accent + neutral greys; the app chrome keeps native
# colors, and the report preview renders on a white page).
_ACCENT = "#185FA5"
_SECONDARY = "#5f5e5a"
_MUTED = "#888780"
_RULE = "#d9d7cf"
_SERIF = "Georgia, 'Times New Roman', serif"
_MONO = "ui-monospace, Menlo, 'SF Mono', monospace"
_BODY = "-apple-system, 'Segoe UI', Roboto, sans-serif"


_DEFAULT_NEXT_STEPS = [
    "Open and review the generated guided pivot links, recording findings by hand.",
    "Verify each located account and email directly before relying on it.",
]


@dataclass
class Citation:
    number: int
    source: str
    url: str | None


@dataclass
class ReportSection:
    title: str
    is_manual: bool
    findings: list[Finding]
    note: str


@dataclass
class ReportContext:
    case: Case
    template: ReportTemplate
    sections: list[ReportSection]
    citations: list[Citation]
    generated_at: datetime
    _numbers: dict[str, int] = field(default_factory=dict)

    def citation_number(self, finding: Finding) -> int:
        return self._numbers[finding.id]

    @property
    def generated_label(self) -> str:
        return self.generated_at.strftime("%Y-%m-%d %H:%M UTC")

    @property
    def key_findings(self) -> str:
        if self.case.key_findings.strip():
            return self.case.key_findings.strip()
        # Neutral prompt only. The tool draws no conclusions; the analyst writes
        # this section. Never assert "no derogatory information" (not established).
        return (
            "[Summarize the key findings here. Automated collection does not draw "
            "conclusions, so this section is written by the analyst.]"
        )

    @property
    def next_steps(self) -> list[str]:
        lines = [line.strip() for line in self.case.next_steps.splitlines()]
        lines = [line.lstrip("-• ").strip() for line in lines if line.strip()]
        return lines or self.template.next_steps or list(_DEFAULT_NEXT_STEPS)

    @property
    def methodology(self) -> str:
        # A template may override the methodology (e.g. KYB names SEC/CourtListener
        # instead of the person collectors); "{subject}" in it is filled here.
        if self.template.methodology:
            return self.template.methodology.replace("{subject}", self.case.subject)
        return (
            f'Searches were performed using the subject value "{self.case.subject}" '
            "and derivatives. Automated collectors run: username presence (Maigret), "
            "email account-existence (Gravatar and holehe), file and photo metadata "
            "(ExifTool), and search-kit link generation. Sources behind logins or "
            "anti-bot controls were not scraped; guided pivot links were generated for "
            "manual review. A finding marked unreachable could not be confirmed at the "
            "time of collection."
        )


def build_report_context(case: Case) -> ReportContext:
    """Build the case's chosen template outline with included findings placed by type."""

    template = get_template(case.template)
    included = case.included_findings()

    citations: list[Citation] = []
    key_to_number: dict[tuple[str, str | None], int] = {}
    numbers: dict[str, int] = {}
    for finding in included:
        key = (finding.source, finding.source_url)
        if key not in key_to_number:
            number = len(citations) + 1
            key_to_number[key] = number
            citations.append(Citation(number, finding.source, finding.source_url))
        numbers[finding.id] = key_to_number[key]

    sections: list[ReportSection] = []
    for spec in template.outline:
        if spec.finding_type is None:
            sections.append(ReportSection(spec.title, True, [], spec.note))
        else:
            # Collected section: fill from findings, but keep any note as guidance
            # (some sections, e.g. Assets/Legal, are only partly automatable).
            found = [f for f in included if f.type == spec.finding_type]
            sections.append(ReportSection(spec.title, False, found, spec.note))

    return ReportContext(
        case=case,
        template=template,
        sections=sections,
        citations=citations,
        generated_at=datetime.now(UTC),
        _numbers=numbers,
    )


# --- outline (report view sidebar) --------------------------------------------

SOURCES_ANCHOR = "sec-sources"


def section_anchor(index: int) -> str:
    return f"sec-{index}"


def report_outline(case: Case) -> list[tuple[str, str]]:
    """Return (title, anchor) pairs for the report view's outline sidebar."""

    ctx = build_report_context(case)
    outline = [("Overview", "top")]
    outline += [(s.title, section_anchor(i)) for i, s in enumerate(ctx.sections)]
    outline.append(("Sources", SOURCES_ANCHOR))
    return outline


# --- HTML (drives the Qt preview and PDF) -------------------------------------


def _esc(text: str) -> str:
    return html.escape(text or "")


def _heading(text: str) -> str:
    # Semantic <h2> so the heading survives into the Word export as a real heading;
    # the serif look is kept with an inline style for the on-screen preview/PDF.
    return f'<h2 style="font-family:{_SERIF}; font-size:15px;">{_esc(text)}</h2>'


def _findings_table(ctx: ReportContext, findings: list[Finding]) -> str:
    rows = [
        '<table cellpadding="5" cellspacing="0" width="100%">',
        f'<tr style="color:{_SECONDARY};">'
        f'<td style="border-bottom:1px solid {_RULE};">Finding</td>'
        f'<td style="border-bottom:1px solid {_RULE};">Confidence</td>'
        f'<td style="border-bottom:1px solid {_RULE};">Notes</td>'
        f'<td style="border-bottom:1px solid {_RULE}; text-align:right;">Source</td>'
        "</tr>",
    ]
    for f in findings:
        rows.append(
            "<tr>"
            f'<td style="border-bottom:1px solid {_RULE};">{_esc(f.value)}</td>'
            f'<td style="border-bottom:1px solid {_RULE};">'
            f"{_esc(f.analyst_confidence.value)}</td>"
            f'<td style="border-bottom:1px solid {_RULE}; color:{_SECONDARY};">'
            f"{_esc(f.notes)}</td>"
            f'<td style="border-bottom:1px solid {_RULE}; text-align:right; '
            f'color:{_ACCENT};">[{ctx.citation_number(f)}]</td>'
            "</tr>"
        )
    rows.append("</table>")
    return "".join(rows)


def _section_inner(ctx: ReportContext, section: ReportSection) -> str:
    """The dynamic body of a collected section (its table, or a 'no results' note)."""
    if section.findings:
        return _findings_table(ctx, section.findings)
    return (
        f'<div style="font-size:12px; color:{_MUTED}; font-style:italic;">'
        "No results were located through automated collection.</div>"
    )


def _sources_inner(ctx: ReportContext) -> str:
    if ctx.citations:
        rows = []
        for cite in ctx.citations:
            url = f" ({_esc(cite.url)})" if cite.url else ""
            rows.append(
                f'<span style="color:{_ACCENT};">[{cite.number}]</span> '
                f"{_esc(cite.source)}{url}"
            )
        return (
            f'<div style="font-family:{_MONO}; font-size:11.5px; '
            f'color:{_SECONDARY}; line-height:1.7;">' + "<br/>".join(rows) + "</div>"
        )
    return f'<p style="color:{_MUTED};"><i>No sources cited yet.</i></p>'


def render_dynamic_parts(case: Case) -> dict[str, str]:
    """The parts of the report that change with curation: findings tables + sources.

    Keyed so the editor can replace them in place (``str(section_index)`` for each
    collected section, and ``"sources"``) without touching the analyst's writing.
    """
    ctx = build_report_context(case)
    parts: dict[str, str] = {}
    for i, section in enumerate(ctx.sections):
        if not section.is_manual:
            parts[str(i)] = _section_inner(ctx, section)
    parts["sources"] = _sources_inner(ctx)
    return parts


def render_html(case: Case) -> str:
    """Render the full due-diligence report as an HTML string (preview and PDF)."""

    ctx = build_report_context(case)
    c = ctx.case
    p: list[str] = ['<a name="top"></a>']

    # Front matter.
    p.append(
        f'<div style="font-size:11px; color:{_MUTED}; letter-spacing:1px;">'
        f"PRIVATE AND CONFIDENTIAL &middot; {_esc(ctx.template.banner)}</div>"
    )
    p.append(
        f'<div style="font-family:{_SERIF}; font-size:20px; margin:2px 0 4px;">'
        f"{_esc(ctx.template.subject_label)}: {_esc(c.subject)}</div>"
    )
    meta = [f"Type: {_esc(c.subject_type.value)}"]
    if c.analyst:
        meta.append(f"Investigator: {_esc(c.analyst)}")
    if c.client:
        meta.append(f"Client: {_esc(c.client)}")
    meta.append(f"Generated: {ctx.generated_label}")
    meta.append(f"Authorized: {'yes' if c.authorized else 'no'}")
    if c.scope_note:
        meta.append(f"Scope: {_esc(c.scope_note)}")
    p.append(
        f'<div style="font-size:12px; color:{_SECONDARY};">'
        + "  &middot;  ".join(meta)
        + "</div>"
    )
    p.append(f'<hr style="border:0; border-top:1px solid {_RULE};"/>')

    p.append(_heading("Key Findings"))
    p.append(f'<div style="font-size:12.5px;">{_esc(ctx.key_findings)}</div>')

    p.append(_heading("Recommended Next Steps"))
    p.append('<ul style="margin-top:2px;">')
    for step in ctx.next_steps:
        p.append(f"<li>{_esc(step)}</li>")
    p.append("</ul>")

    p.append(_heading("Search Methodology"))
    p.append(f'<div style="font-size:12.5px; color:{_SECONDARY};">{_esc(ctx.methodology)}</div>')

    # Body sections. Collected sections' bodies live in data-dsec containers so the
    # editor can refresh just them when curation changes, leaving analyst text alone.
    for i, section in enumerate(ctx.sections):
        p.append(f'<a name="{section_anchor(i)}"></a>')
        p.append(_heading(section.title))
        if section.is_manual:
            p.append(
                f'<div style="font-size:12px; color:{_MUTED}; font-style:italic;">'
                f"To complete: {_esc(section.note)}</div>"
            )
        else:
            p.append(f'<div data-dsec="{i}">{_section_inner(ctx, section)}</div>')
            if section.note:  # partly-automatable section: show manual guidance too
                p.append(
                    f'<div style="font-size:12px; color:{_MUTED}; font-style:italic; '
                    f'margin-top:4px;">To complete: {_esc(section.note)}</div>'
                )

    # Sources (also curation-driven).
    p.append(f'<a name="{SOURCES_ANCHOR}"></a>')
    p.append(_heading("Sources"))
    p.append(f'<div data-dsrc="1">{_sources_inner(ctx)}</div>')

    body = f'<html><body style="font-family:{_BODY}; color:#1a1a18;">'
    return body + "".join(p) + "</body></html>"
