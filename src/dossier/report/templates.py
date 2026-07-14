"""Report templates: named section outlines for different investigation types.

A template is just a section outline plus a little framing (the confidential
banner, whether the subject is a person or an entity, default next steps, and an
optional methodology override). The report engine (``render.py``) is otherwise
identical across templates: the same findings, the same citation builder, the
same auto-fill-by-``FindingType`` rule. A section with a ``finding_type`` is
auto-filled from findings of that type; a section with only a ``note`` is an
analyst-completed scaffold, because that data needs sources Dossier does not
touch. Nothing is faked either way.

This module is Qt-free and imports only the data model.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import FindingType


@dataclass
class SectionSpec:
    """One section of a report outline.

    ``finding_type`` None marks an analyst-completed (manual) section carrying a
    scaffolding ``note``; otherwise the section is auto-filled from findings of
    that type (and may still carry a ``note`` when it is only partly automatable).
    """

    title: str
    finding_type: FindingType | None = None
    note: str = ""


@dataclass
class ReportTemplate:
    """A named investigation report layout.

    Attributes:
        key: Stable identifier stored on the case (never shown to the user).
        name: Human label for the template picker.
        description: One-line explanation for the picker.
        banner: Suffix of the "PRIVATE AND CONFIDENTIAL" front-matter line.
        subject_label: What the subject is called in the front matter
            ("Subject" for a person, "Entity" for a company).
        outline: The ordered sections.
        next_steps: Default "Recommended Next Steps" when the analyst has not
            written their own.
        methodology: Optional override for the Search Methodology paragraph.
            Empty means use the engine's generic person-oriented text.
    """

    key: str
    name: str
    description: str
    banner: str
    subject_label: str
    outline: list[SectionSpec]
    next_steps: list[str] = field(default_factory=list)
    methodology: str = ""


# --- the person "full background" due-diligence report (the default) ----------

DUE_DILIGENCE = ReportTemplate(
    key="due_diligence",
    name="Full Background Investigation",
    description="Person due-diligence: the complete CYBV 354 background layout.",
    banner="FULL BACKGROUND INVESTIGATION",
    subject_label="Subject",
    outline=[
        SectionSpec(
            "Personal & Residence",
            note=(
                "Identity details (date of birth, current and prior addresses) are not "
                "collected by automated public tools. Complete this section manually "
                "from public-records sources."
            ),
        ),
        SectionSpec("Email Addresses", FindingType.EMAIL),
        SectionSpec("Social Media & Online Presence", FindingType.ACCOUNT),
        SectionSpec(
            "Assets & Liabilities",
            FindingType.BUSINESS,
            note=(
                "Automated results below cover public business registrations and filings "
                "(e.g. SEC). Property and vehicle records need public-records databases; "
                "complete those manually."
            ),
        ),
        SectionSpec(
            "Professional Development",
            note=(
                "Education, certifications, professional licenses and disciplinary "
                "actions, and employment history. Verify manually and note verified "
                "versus self-reported."
            ),
        ),
        SectionSpec(
            "Legal",
            FindingType.LEGAL,
            note=(
                "Automated results below cover public court records (e.g. CourtListener). "
                "Liens, foreclosure, bankruptcy, evictions, and criminal and "
                "sexual-offender records need agency sources; complete those manually."
            ),
        ),
        SectionSpec("Media, Social Networks & Open Sources", FindingType.LINK),
        SectionSpec("Exhibits & Digital Artifacts", FindingType.METADATA),
    ],
    next_steps=[
        "Open and review the generated guided pivot links, recording findings by hand.",
        "Verify each located account and email directly before relying on it.",
        "Complete the Assets, Professional Development, and Legal sections from public records.",
    ],
)


# --- TraceLabs missing-person OSINT report ------------------------------------

# Sections mirror the TraceLabs Search Party CTF flag categories (with their point
# weights) so a competitor's findings line up 1:1 with how they are scored.
# Categories and points: TraceLabs flag-categories guide
# (github.com/C3n7ral051nt4g3ncy/TraceLabs-Flag-Categories-Guide) and
# docs.tracelabs.org. Conduct rules: https://www.tracelabs.org/about/search-party-rules
TRACELABS = ReportTemplate(
    key="tracelabs",
    name="Missing Person (TraceLabs)",
    description="Missing-person OSINT in the TraceLabs Search Party structure.",
    banner="MISSING PERSON OSINT REPORT",
    subject_label="Subject",
    outline=[
        SectionSpec(
            "Basic Subject Information",  # TraceLabs "Basic Subject Info" (50 pts)
            note=(
                "Core identity: full name, aliases, date of birth or age, physical "
                "description, and identifying marks. Passive only: view but never "
                "engage, and never contact the subject, their family, or associates."
            ),
        ),
        SectionSpec(
            "Advanced Subject Information",  # TraceLabs "Advanced Subject Info" (100 pts)
            note=(
                "Deeper identifiers beyond the basics: usernames and handles, phone "
                "numbers, vehicles, and other distinguishing intelligence. The located "
                "accounts and emails below feed this category."
            ),
        ),
        SectionSpec("Social Media & Online Accounts", FindingType.ACCOUNT),
        SectionSpec("Email & Contact Points", FindingType.EMAIL),
        SectionSpec(
            "Friends, Family & Associates",  # TraceLabs "Friends" (10 pts)
            note=(
                "People connected to the subject (relatives, partners, close contacts). "
                "Pivot from the located accounts; for each person record the relationship "
                "and how you established it. Do not interact with them."
            ),
        ),
        SectionSpec(
            "Employment",  # TraceLabs "Employment" (15 pts)
            note=(
                "Current and previous employers. Verify each and note verified versus "
                "self-reported."
            ),
        ),
        SectionSpec(
            "Day Last Seen",  # TraceLabs "Day Last Seen" (300 pts)
            note=(
                "Everything tied to the disappearance date: last-known location, "
                "clothing, companions, vehicle, and the circumstances of that day. "
                "Record only facts, never theories."
            ),
        ),
        SectionSpec(
            "Advancing the Timeline",  # TraceLabs "Advancing the Timeline" (700 pts)
            note=(
                "Evidence of the subject's activity AFTER the missing date (posts, "
                "logins, sightings, transactions). High-value: it extends the timeline "
                "past the last confirmed point."
            ),
        ),
        SectionSpec(
            "Location Intelligence",  # TraceLabs "Location" (5000 pts) - highest value
            FindingType.METADATA,
            note=(
                "The subject's current or most recent location is the highest-value "
                "intelligence. Geolocation from image metadata (EXIF) appears below; "
                "extend it with GEOINT from posts, backgrounds, and check-ins by hand."
            ),
        ),
        SectionSpec(
            "Dark Web & Breach Exposure",  # TraceLabs "Darkweb" (1000 pts)
            note=(
                "Any presence of the subject on dark-web sources or in breach data. Use "
                "the generated guided links; do not attempt account access."
            ),
        ),
        SectionSpec("Leads & Guided Pivots", FindingType.LINK),
    ],
    next_steps=[
        "Prioritise recent location and post-disappearance timeline intelligence: "
        "TraceLabs scores Location (5000) and Advancing the Timeline (700) highest.",
        "Stay strictly passive (zero touch): view but never engage. Contacting the "
        "subject, their family, or friends, including tagging, friending, or liking, "
        "is grounds for disqualification.",
        "Deal only in facts. Do not theorise or speculate in the report.",
        "For every associate located, record the relationship and how you established it.",
        "Do not contact law enforcement or the media directly; route all intelligence "
        "through your coach or the TraceLabs team.",
    ],
    methodology=(
        'Searches were performed using the subject value "{subject}" and derivatives, '
        "under TraceLabs passive-reconnaissance rules: information was viewed but never "
        "engaged (zero touch), and no contact was made with the subject, their family, "
        "or associates. Automated collectors run: username presence (Maigret), email "
        "account-existence (Gravatar and holehe), file and photo metadata (ExifTool), "
        "and search-kit link generation. Sources behind logins or anti-bot controls were "
        "not scraped; guided pivot links were generated for manual review. A finding "
        "marked unreachable could not be confirmed at the time of collection."
    ),
)


# --- company / entity (KYB) due diligence -------------------------------------

# Structure follows standard KYB practice: (1) business identity and registration,
# (2) beneficial-ownership identification, (3) risk assessment and ongoing monitoring,
# with sanctions/PEP/adverse-media screening throughout. The 25% ultimate-beneficial-
# owner threshold: FATF Recommendations 24 & 25 (2023 update); US FinCEN CDD rule;
# EU AML directives. (Sources: sumsub.com/blog/kyb-guide, dotfile.com end-to-end KYB.)
KYB = ReportTemplate(
    key="kyb",
    name="Company / Entity (KYB)",
    description="Corporate due diligence: identity, filings, ownership, litigation, screening.",
    banner="CORPORATE DUE DILIGENCE",
    subject_label="Entity",
    outline=[
        SectionSpec(
            "Corporate Identity",
            note=(
                "Legal name, DBAs and aliases, registration number, jurisdiction and date "
                "of incorporation, and current status. Verify against the primary company "
                "registry (Secretary of State, Companies House, or the relevant equivalent)."
            ),
        ),
        SectionSpec("Registrations & Filings", FindingType.BUSINESS),
        SectionSpec(
            "Ownership & Beneficial Owners",
            note=(
                "Ownership structure and every ultimate beneficial owner (UBO): each "
                "individual who owns or controls 25% or more, or otherwise exercises "
                "control (FATF Recommendations 24 and 25; US FinCEN CDD rule; EU AML "
                "directives). Trace ownership through intermediate entities. Complete from "
                "corporate registries and beneficial-ownership databases."
            ),
        ),
        SectionSpec(
            "Officers & Management",
            note=(
                "Directors, officers, and senior management. The SEC filings above may "
                "name insiders; corporate registries complete this."
            ),
        ),
        SectionSpec("Litigation & Legal", FindingType.LEGAL),
        SectionSpec(
            "Sanctions, PEP & Watchlist Screening",
            note=(
                "Screen the entity and every named principal and UBO against sanctions "
                "and watchlists (OFAC, EU, and UN consolidated lists), politically exposed "
                "person (PEP) databases, and law-enforcement lists. Record each list "
                "checked and the result."
            ),
        ),
        SectionSpec(
            "Adverse Media",
            note=(
                "Negative news and regulatory actions involving the entity or its "
                "principals, from reputable sources. Note the source and date of each item."
            ),
        ),
        SectionSpec("Web & Domain Footprint", FindingType.LINK),
        SectionSpec(
            "Risk Assessment",
            note=(
                "Overall money-laundering and reputational risk rating, reasoned from "
                "jurisdiction, industry, ownership complexity, and the screening results "
                "above. Note whether standard or enhanced due diligence applies, and any "
                "ongoing-monitoring triggers."
            ),
        ),
        SectionSpec("Digital Artifacts", FindingType.METADATA),
    ],
    next_steps=[
        "Confirm the entity's registration and current status with the primary registry.",
        "Identify every beneficial owner at the 25% ownership-or-control threshold and "
        "trace ownership through intermediate entities.",
        "Screen the entity, principals, and UBOs against sanctions (OFAC, EU, UN) and PEP lists.",
        "Complete adverse-media screening from reputable news sources.",
        "Assign an overall risk rating and record any ongoing-monitoring triggers.",
    ],
    methodology=(
        'Searches were performed using the entity name "{subject}" and its derivatives. '
        "Automated collectors run: SEC EDGAR full-text filing search and CourtListener "
        "federal court records, plus search-kit link generation for company registries "
        "and news. Sources behind logins or anti-bot controls were not scraped; guided "
        "pivot links were generated for manual review. A finding marked unreachable could "
        "not be confirmed at the time of collection."
    ),
)


# --- one-page subject profile (condensed) -------------------------------------

PROFILE = ReportTemplate(
    key="profile",
    name="One-Page Subject Profile",
    description="A quick, collected-only snapshot: accounts, email, leads, metadata.",
    banner="SUBJECT PROFILE",
    subject_label="Subject",
    outline=[
        SectionSpec("Online Accounts", FindingType.ACCOUNT),
        SectionSpec("Email", FindingType.EMAIL),
        SectionSpec("Leads & Open Sources", FindingType.LINK),
        SectionSpec("Metadata", FindingType.METADATA),
    ],
    next_steps=[
        "Verify each located account and email directly before relying on it.",
        "Open the guided pivot links and record anything relevant by hand.",
    ],
)


# --- registry -----------------------------------------------------------------

DEFAULT_TEMPLATE = DUE_DILIGENCE.key

TEMPLATES: dict[str, ReportTemplate] = {
    t.key: t for t in (DUE_DILIGENCE, TRACELABS, KYB, PROFILE)
}


def get_template(key: str) -> ReportTemplate:
    """Return the template for ``key``, falling back to the default if unknown."""

    return TEMPLATES.get(key, TEMPLATES[DEFAULT_TEMPLATE])
