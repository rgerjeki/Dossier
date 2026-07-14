"""Qt-side report output: Word export.

The report content comes from the editable document in the report editor. PDF is
exported by the editor itself (Chromium's print engine). Word is converted from
the document's HTML here.
"""

from __future__ import annotations

from pathlib import Path


def html_to_docx(html: str, path: Path | str) -> Path:
    """Convert report HTML to a Word ``.docx`` (via htmldocx)."""

    from docx import Document
    from htmldocx import HtmlToDocx

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    document = Document()
    HtmlToDocx().add_html_to_document(html, document)
    document.save(str(path))
    return path
