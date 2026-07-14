"""Tests for the web-based report editor. Requires QtWebEngine (Chromium).

These spin up a real browser document and use an event loop, so they are slower
than the rest of the suite. They verify the thing QTextEdit got wrong: that the
document round-trips without the formatting drifting.
"""

from __future__ import annotations

import os

import pytest

# Opt-in and skip FIRST, before importing QtWebEngine: Chromium is unstable when
# many views are created in one headless run, and merely importing it alongside
# the rest of the suite can crash. Enable with DOSSIER_WEBTEST=1.
if os.environ.get("DOSSIER_WEBTEST") != "1":
    pytest.skip("web-editor tests need DOSSIER_WEBTEST=1", allow_module_level=True)

pytest.importorskip("PySide6.QtWebEngineWidgets")

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from dossier.ui.report_editor import ReportEditor  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _pump(ms: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def test_content_round_trips_without_format_drift(qapp) -> None:
    editor = ReportEditor()
    _pump(1500)  # let the page load
    report = (
        '<h2 style="font-family:Georgia">Key Findings</h2>'
        "<p>Plain body sentence the analyst wrote.</p>"
        "<p><b>Bold note</b> and <i>italic</i> text.</p>"
    )
    editor.set_content(report)
    _pump(1500)  # let it apply and mirror back

    content = editor.content()
    assert "<h2" in content.lower()
    # The plain paragraph must NOT have become bold/heading (the QTextEdit bug).
    assert "Plain body sentence the analyst wrote." in content
    assert "<b>Plain body" not in content
    # Explicit formatting is preserved.
    assert "<b>Bold note</b>" in content or "font-weight" in content.lower()


def test_edit_signal_updates_content(qapp) -> None:
    editor = ReportEditor()
    _pump(800)
    seen = []
    editor.contentEdited.connect(lambda: seen.append(editor.content()))
    editor._bridge.onInput("<p>typed by the analyst</p>")  # simulate a JS edit
    assert editor.content() == "<p>typed by the analyst</p>"
    assert seen and "typed by the analyst" in seen[-1]


def test_update_dynamic_patches_findings_not_narrative(qapp) -> None:
    editor = ReportEditor()
    _pump(1500)
    doc = (
        '<div data-dsec="0"><table><tr><td>OLDFINDING</td></tr></table></div>'
        "<p>My analysis paragraph.</p>"
        '<div data-dsrc="1">old sources</div>'
    )
    editor.set_content(doc)
    _pump(1200)
    editor.update_dynamic(
        {"0": "<table><tr><td>NEWFINDING</td></tr></table>", "sources": "new sources"}
    )
    _pump(1200)

    content = editor.content()
    assert "NEWFINDING" in content and "OLDFINDING" not in content  # findings patched
    assert "new sources" in content and "old sources" not in content
    assert "My analysis paragraph." in content  # analyst text preserved


def test_insert_image_embeds_data_uri(qapp) -> None:
    editor = ReportEditor()
    _pump(1500)
    editor.set_content("<p>before</p>")
    _pump(1000)
    # Simulate Python handing the picked image to the page (skips the file dialog).
    editor._bridge.insertImage.emit("data:image/png;base64,AAAABBBB")
    _pump(1000)

    content = editor.content()
    assert "<img" in content
    assert "data:image/png;base64,AAAABBBB" in content
    assert "before" in content  # existing content preserved


def test_image_resize_persists_and_overlay_stays_out_of_content(qapp) -> None:
    editor = ReportEditor()
    editor._view.resize(1000, 800)  # give the page a known width to clamp against
    _pump(1500)
    editor.set_content('<p>a</p><img src="data:image/png;base64,AAAA">')
    _pump(1000)
    # Headless can't do a real mouse drag, so drive the exact globals the corner
    # handle uses: select the image, then run one drag step and commit. Shrink
    # (start 120 -> 50) so the result stays clear of the page-width upper clamp,
    # which is small in an unshown offscreen layout.
    editor._view.page().runJavaScript(
        "var im=document.querySelector('#doc img');"
        "selectImg(im); dragging=true; startX=0; startW=120;"
        "onImgDrag({clientX:-70}); endImgDrag();"
    )
    _pump(1000)

    content = editor.content()
    assert "width: 50px" in content  # the resize persisted onto the image
    # The selection overlay must never become part of the saved document.
    assert "imgSel" not in content and "imgHandle" not in content
    assert "data:image/png;base64,AAAA" in content  # image itself intact


def test_print_pdf_writes_a_file(qapp, tmp_path) -> None:
    editor = ReportEditor()
    _pump(1200)
    editor.set_content("<h1>Report</h1><p>Body text for the PDF.</p>")
    _pump(1000)

    out = tmp_path / "r.pdf"
    done = []
    editor.print_pdf(str(out), lambda ok: done.append(ok))
    # printToPdf is asynchronous; wait for the finished callback.
    for _ in range(20):
        if done:
            break
        _pump(500)
    assert done and done[0] is True
    assert out.exists() and out.stat().st_size > 0
