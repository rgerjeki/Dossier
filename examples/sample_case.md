# Sample case

This folder holds a sanitized sample investigation, safe to read and share:

- `sample_case.json` is a saved Dossier case. Open it in the app with **Open
  case...** to see the curation view populated.
- `sample_report.docx` and `sample_report.pdf` are the report exported from that
  case, with each finding mapped into its section and every source cited.

## About the subject

The subject, `ada_example`, is a **fictional persona**, not a real person. Every
finding is fabricated for documentation. This follows the project's rule (see the
legal and ethical section in [`../README.md`](../README.md)): anything public
(screenshots, samples, the portfolio) uses a safe target only, never a real
private individual.

The sample deliberately shows the whole loop:

- findings from every collector type (username, email, metadata, guided link),
- an included/excluded split (7 of 8 findings kept), so curation is visible,
- an "unreachable" finding, so honest degradation is visible,
- a per-finding analyst confidence and notes,
- a numbered, de-duplicated source list generated from the findings.

## Regenerating

The sample is generated from code, so it stays in sync with the report format.
See the generator used to build it in the project history, or rebuild a case of
your own by running the app on a safe target.
