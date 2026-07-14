# Packaging Dossier as a standalone macOS app

This builds `Dossier.app`, a double-click app that bundles Python, Qt, and a full
Chromium (QtWebEngine) so the end user never installs Python or a virtualenv.

## Build

From the repo root, with the project venv active and the `ui`, `report`, and
`collectors` extras installed (plus `pyinstaller`):

```bash
pip install pyinstaller
pyinstaller packaging/Dossier.spec --noconfirm \
  --distpath ~/Applications/dossier-dist \
  --workpath /tmp/dossier-build
```

The finished app is `~/Applications/dossier-dist/Dossier.app`. Move it into
`/Applications` (or `~/Applications`) to use it.

## Two hard rules (both learned the hard way)

1. **Never build or run from a cloud-sync / File Provider folder** (FileBox,
   iCloud Drive, Dropbox, OneDrive). Qt finds its bundled plugins by *enumerating*
   a directory, and those virtualized filesystems return an empty listing, so Qt
   aborts with "Could not find the Qt platform plugin cocoa". The `--distpath` and
   `--workpath` above are deliberately on local disk. The shipped app must also
   *run* from local disk (`/Applications`), not from a synced folder.
2. **Use Python 3.11-3.13, never 3.14.** PySide6 6.11 does not support 3.14.

## What the app writes, and where

A bundled app has no meaningful working directory, so cases and exports go to a
per-user data directory instead of a folder next to the app
(`src/dossier/case.py`, `app_data_dir()`):

- macOS: `~/Library/Application Support/Dossier/{cases,exports}`

`DOSSIER_CASES_DIR` / `DOSSIER_EXPORTS_DIR` still override this if set.

## External dependency: exiftool

The metadata collector shells out to the `exiftool` binary, which is **not**
bundled. Without it, metadata extraction reports "not run" and everything else
works. Document `brew install exiftool` for users who need photo/file metadata,
or bundle the binary in a later iteration.

## Size

The app is ~570MB. The bulk is QtWebEngine (Chromium), which is mandatory for the
report editor and cannot be removed; this is normal for any Chromium-embedding
desktop app (Electron apps are similar). The spec already excludes unused Python
modules and Qt bindings. Further trimming (dropping leftover unused Qt frameworks
via a TOC filter) is possible but must be re-tested against a working editor.

## Signing and distribution (important limitation)

PyInstaller ad-hoc signs the bundle, which is enough to run on the machine that
built it. To distribute it to other Macs without a Gatekeeper block
("Apple cannot check it for malicious software"), the app must be **signed with a
Developer ID certificate and notarized by Apple**, which requires a paid Apple
Developer account and your credentials. That step is not automated here. Until
then, other users can run it via right-click -> Open, or:

```bash
xattr -dr com.apple.quarantine /Applications/Dossier.app
```

## TODO

- App icon (`packaging/Dossier.icns`, wired into the spec's `BUNDLE(icon=...)`).
- Developer ID signing + notarization for clean distribution.
- Optional: bundle the `exiftool` binary; optional Qt-framework size trim.
