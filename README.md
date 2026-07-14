# Dossier

An offline OSINT investigation workbench. Dossier runs a single investigation
from collection all the way to a finished, cited report. It is built around one
loop: collect, curate, report.

1. **Collect:** open a case on a subject (a username, email, name, or a file) and
   run automated OSINT collectors.
2. **Curate:** the results appear in the app, and the investigator picks the
   findings that matter into the case. This human-judgment step stays inside the
   tool.
3. **Report:** the kept findings flow into a due-diligence report template, the
   investigator adds narrative and analysis, and it exports a finished Word or
   PDF document with the sources cited automatically.

The mental model is "a Word template that also does data collection." Collection
feeds the workbench, the human curates, and the report writes itself from what
was kept.

## Where Dossier fits

Dossier is built around one idea: for a solo investigator, the hard part is not
running a scanner, it is turning the results into a formatted, cited report you
can stand behind.

- **It reuses best-in-class collectors** (Maigret, holehe, and friends) instead of
  reinventing them, and puts its own effort into the piece that is genuinely thin
  for the individual investigator: findings flow into a due-diligence report with
  every fact tracked back to its source and ready to export.
- **It covers the whole lifecycle in one offline app:** collect, curate, analyze,
  write, and cite, without shuttling data between five separate tools.
- **Built for the individual investigator:** students, small shops, journalists,
  CTF and TraceLabs players, and personal research, where a lightweight,
  end-to-end, offline workbench is more useful than an enterprise suite.

## What it collects (and what it deliberately does not)

Clear boundaries are a feature here, because honest provenance is the whole point:

- **Automated, real data** from public, no-login sources: username presence, email
  account-existence, file and photo metadata, Gravatar, SEC EDGAR filings,
  CourtListener records, and search-link generation.
- **Guided, not scraped, for walled sources.** For anything behind a login or
  anti-bot wall (Instagram, LinkedIn, X, most people-search and public-records
  sites), Dossier generates precise pivot links you open and review by hand,
  rather than fragile scrapers that break constantly and violate terms. This is
  how professional OSINT actually works, and it keeps the tool stable and legal.
- **Nothing is faked.** A collector that is blocked, rate limited, or unreachable
  is reported as exactly that, never dropped silently or invented. Collectors run
  politely (timeouts and delays) and each finding carries an honest status.

## Responsible use

Dossier is a general OSINT tool, like Maltego, SpiderFoot, or Maigret. It does not
gate or restrict who you investigate, and it never tries to judge whether a given
target is "authorized." That judgment, and the legal responsibility for it, sits
with you, the operator. You are accountable for using it lawfully and within the
terms of the services involved.

What the tool does hold itself to is integrity, not restriction:

- **It does not fabricate.** A collector that is blocked, rate limited, or
  unreachable is reported as such, never dropped or invented. The report never
  states a conclusion the data does not support.
- **It does not scrape walled sites.** Sources behind logins or anti-bot controls
  (most social, people-search, and public-records sites) return real data only to
  a real browser, so Dossier generates guided pivot links you open and review by
  hand rather than fragile scrapers that break or violate terms. This is how
  professional OSINT actually works.
- **It is passive.** Nothing notifies or contacts a subject.

Practical notes:

- **Investigation output is sensitive.** Case files and exports live in gitignored
  directories (`cases/`, `exports/`) and are not committed.
- **Each case has an optional scope/consent note.** It is documentation for your
  own records (the tradecraft habit of writing down your authorization), not a
  lock; nothing enforces it.
- **For anything you publish** (screenshots, a portfolio write-up), use a target
  you are comfortable making public, yourself, a public figure, a seeded persona,
  or a sanctioned CTF like TraceLabs. That is advice about what you publish, not a
  limit on what the tool will do.

## Status

The full v1 loop works: collect, curate, report.

- Collectors: username presence (Maigret), GitHub profile, Keybase proven
  accounts, email (Gravatar built here, plus holehe when installed), SEC EDGAR
  filings, CourtListener court records, file/photo metadata (ExifTool), and a
  search-kit of guided pivot links for the walled sources (people/address,
  reverse image, breach, social) that only return data to a real browser. Each
  returns normalized findings with an honest per-finding status.
- Curation: findings land in a local case; mark which to include, edit notes, and
  set an analyst confidence per finding.
- Report: included findings render into a chosen report template, a full
  Background Investigation, a TraceLabs missing-person report, a company / entity
  (KYB) due-diligence report, or a one-page profile. Collected sections (emails,
  social presence, media and open-source links, metadata exhibits, and for KYB the
  SEC filings and court records) auto-fill with a numbered, de-duplicated source
  list; sections that need paid or manual records are scaffolded with an honest
  note to complete by hand. The report opens as a fully editable document (type
  and edit anywhere, drag images to resize), and your edits drive both exports:
  PDF (exact, via Chromium) and Word `.docx`.

See [`examples/`](examples/) for a sanitized sample case and its exported report.

## Download (macOS)

A prebuilt, self-contained macOS app is attached to each release, no Python or
setup required. Download the latest `Dossier-macOS-arm64-*.zip` from the
[Releases](../../releases) page, unzip it, and drag `Dossier.app` into
`/Applications`.

**Requirements:** Apple Silicon (M1 or later), macOS 11 or newer. This build is
arm64-only and will not run on Intel Macs. Intel, Windows, and Linux builds are
not yet available; on those platforms, run from source (below).

The app is not yet notarized by Apple, so the first launch needs one extra step:
right-click `Dossier.app`, choose **Open**, and confirm (or run
`xattr -dr com.apple.quarantine /Applications/Dossier.app`). After that it opens
normally. Keep the app on local disk (`/Applications`), not inside a cloud-sync
folder such as iCloud Drive or Dropbox, or Qt cannot find its plugins and the app
will not start.

Photo and file metadata extraction also needs the `exiftool` binary
(`brew install exiftool`); everything else works out of the box.

## Running from source

```bash
python3.13 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,ui,report]"     # engine + UI + Word export
pip install -e ".[collectors]"        # optional: Maigret, holehe, ExifTool binding
python run.py                         # launch the desktop app
```

Use Python 3.11, 3.12, or 3.13. **Do not use Python 3.14:** PySide6 does not
support it yet, and its Qt plugin layer corrupts on that combo (the platform
plugin fails to load with "Could not find the Qt platform plugin cocoa"). If you
hit that error, you are almost certainly on 3.14; rebuild the venv with
`python3.13`.

**Keep the virtualenv off cloud-sync / File Provider folders** (Box, Dropbox,
iCloud Drive, OneDrive). Qt discovers its plugins by enumerating a directory, and
those virtualized filesystems return empty listings to Qt's enumeration API even
though the files are present, so Qt cannot find its platform plugin and aborts
with the same "cocoa" error. If your project lives inside such a folder, put the
venv on local disk and symlink it in:

```bash
python3.13 -m venv ~/.dossier-venv        # real disk, outside the synced tree
ln -s ~/.dossier-venv .venv               # keep the usual .venv path
source .venv/bin/activate
pip install -e ".[dev,ui,report]" && pip install -e ".[collectors]"
```

Use `python run.py` to launch. It puts `src` on the path explicitly, so it works
even where the editable install's path hook is not honored. `python -m dossier`
and the `dossier` command also work when the editable install is healthy.

The metadata collector also needs the `exiftool` binary on your PATH
(`brew install exiftool` on macOS). Everything else runs against public endpoints
or locally, with no API keys.

To work on the engine alone (no Qt), `pip install -e ".[dev]"` pulls in just the
test tooling, and `pytest` runs the full suite headless.

## Architecture (short version)

The engine and the UI are separated on purpose. The collectors, the `Finding`
data model, and the report renderer are built and tested with no Qt imported.
The PySide6 desktop app is a thin shell over that engine.

Key recorded decisions:

- **Desktop UI:** PySide6 (Qt).
- **Username collector:** Maigret (library-usable, structured JSON, exposes
  claimed vs confirmed status, which matters because provenance is the point).
- **Report render:** one HTML document is the single source of truth. Included
  findings flow through a **shared citation builder** into a chosen report
  template (full background investigation, TraceLabs missing-person, company /
  entity KYB, or a one-page profile), and the result opens in an editable
  QtWebEngine (Chromium) document the analyst edits directly. That same edited
  document drives both exports, so what you see is what ships: PDF via Chromium's
  print engine (exact), and Word `.docx` via `htmldocx`. An earlier design used
  `docxtpl` plus Qt's `QTextDocument` / `QPdfWriter`, but `QTextDocument` renders
  only Qt's rich-text HTML subset and drifted the formatting on save/reopen, so
  the editor was rebuilt on QtWebEngine.

## License

MIT. See [`LICENSE`](LICENSE).
