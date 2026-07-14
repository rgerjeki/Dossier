"""A Word-like report editor built on QtWebEngine (Chromium).

QTextEdit could not round-trip the report's rich HTML without drifting the
formatting on save/reopen. This editor hosts a real browser document
(``contenteditable``) with a formatting toolbar, so what you type is exactly what
is saved and exported. Content is mirrored to Python over a ``QWebChannel`` on
every edit, so ``content()`` is always current for save and export.
"""

from __future__ import annotations

import base64
import json
import mimetypes
from pathlib import Path

from PySide6.QtCore import QFile, QIODevice, QObject, QUrl, Signal, Slot
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QFileDialog, QVBoxLayout, QWidget


def _qwebchannel_js() -> str:
    """Read Qt's bundled qwebchannel.js so it can be inlined (no external load)."""
    f = QFile(":/qtwebchannel/qwebchannel.js")
    if not f.open(QIODevice.OpenModeFlag.ReadOnly):
        return ""
    try:
        return bytes(f.readAll()).decode("utf-8")
    finally:
        f.close()


_PAGE_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  html, body {{ margin: 0; height: 100%; background: #e9e8e4;
    font-family: -apple-system, "Segoe UI", Roboto, sans-serif; }}
  #toolbar {{ position: sticky; top: 0; z-index: 10; display: flex; gap: 4px;
    align-items: center; flex-wrap: wrap; padding: 6px 8px; background: #f3f2ee;
    border-bottom: 1px solid #d7d5cd; }}
  #toolbar button, #toolbar select {{ font-size: 13px; padding: 3px 8px;
    border: 1px solid #cfcdc4; background: #fff; border-radius: 4px; cursor: pointer; }}
  #toolbar button:active {{ background: #e6f1fb; }}
  #wrap {{ padding: 18px; overflow: auto; height: calc(100% - 42px); box-sizing: border-box; }}
  #doc {{ background: #fff; color: #1a1a18; max-width: 8.5in; margin: 0 auto;
    padding: 0.7in; min-height: 9in; box-shadow: 0 1px 6px rgba(0,0,0,.18);
    font-size: 11pt; line-height: 1.4; outline: none; }}
  #doc h1 {{ font-family: Georgia, "Times New Roman", serif; font-size: 20pt; }}
  #doc h2 {{ font-family: Georgia, "Times New Roman", serif; font-size: 14pt; }}
  #doc table {{ border-collapse: collapse; width: 100%; }}
  #doc td {{ padding: 4px 6px; }}
  #doc img {{ cursor: default; }}
  /* Selection overlay for image resize. Lives outside #doc so it never becomes
     part of the saved/exported document; only the image's own width persists. */
  #imgSel {{ position: fixed; display: none; border: 2px solid #4a90d9;
    box-sizing: border-box; pointer-events: none; z-index: 50; }}
  #imgHandle {{ position: absolute; right: -7px; bottom: -7px; width: 12px;
    height: 12px; background: #fff; border: 2px solid #4a90d9; box-sizing: border-box;
    border-radius: 2px; cursor: nwse-resize; pointer-events: auto; }}
</style>
</head>
<body>
<div id="toolbar">
  <button data-cmd="undo" title="Undo">&#8630;</button>
  <button data-cmd="redo" title="Redo">&#8631;</button>
  <button data-cmd="bold" title="Bold"><b>B</b></button>
  <button data-cmd="italic" title="Italic"><i>I</i></button>
  <button data-cmd="underline" title="Underline"><u>U</u></button>
  <select id="block" title="Paragraph style">
    <option value="p">Body</option>
    <option value="h1">Title</option>
    <option value="h2">Heading</option>
  </select>
  <button data-cmd="insertUnorderedList" title="Bulleted list">&bull; List</button>
  <button data-cmd="insertOrderedList" title="Numbered list">1. List</button>
  <button data-cmd="justifyLeft" title="Align left">&#8676;</button>
  <button data-cmd="justifyCenter" title="Align center">&#8596;</button>
  <button data-cmd="justifyRight" title="Align right">&#8677;</button>
  <button id="linkBtn" title="Insert link">Link</button>
  <button id="imgBtn" title="Insert image">Image</button>
  <button data-cmd="removeFormat" title="Clear formatting">Clear</button>
</div>
<div id="wrap"><div id="doc" contenteditable="true"></div></div>
<div id="imgSel"><div id="imgHandle"></div></div>
<script>{qwebchannel}</script>
<script>
  var doc = document.getElementById('doc');
  var bridge = null;
  function notify() {{ if (bridge) bridge.onInput(doc.innerHTML); }}
  function setDoc(html) {{ deselect(); doc.innerHTML = html; }}
  function updateDynamic(parts) {{
    // Replace just the findings tables / sources in place (leave analyst text).
    for (var key in parts) {{
      var sel = (key === 'sources') ? '[data-dsrc]' : '[data-dsec="' + key + '"]';
      var el = doc.querySelector(sel);
      if (el) el.innerHTML = parts[key];
    }}
    notify();
    placeSel();  // patched tables may have shifted a selected image
  }}
  // preventDefault on mousedown keeps the document selection when a toolbar
  // control is clicked (the browser equivalent of a non-focusable toolbar).
  document.querySelectorAll('#toolbar [data-cmd]').forEach(function(btn) {{
    btn.addEventListener('mousedown', function(e) {{ e.preventDefault(); }});
    btn.addEventListener('click', function() {{
      document.execCommand(btn.getAttribute('data-cmd'), false, null);
      doc.focus(); notify();
    }});
  }});
  var block = document.getElementById('block');
  block.addEventListener('mousedown', function(e) {{ /* allow select popup */ }});
  block.addEventListener('change', function() {{
    document.execCommand('formatBlock', false, block.value);
    doc.focus(); notify();
  }});
  // Link: prompt for a URL and link the selected text.
  var linkBtn = document.getElementById('linkBtn');
  linkBtn.addEventListener('mousedown', function(e) {{ e.preventDefault(); }});
  linkBtn.addEventListener('click', function() {{
    var url = prompt('Link URL', 'https://');
    if (url) {{ doc.focus(); document.execCommand('createLink', false, url); notify(); }}
  }});
  // Image: the file picker lives in Python; we keep the caret so the image lands
  // where it was requested.
  var savedRange = null;
  function saveRange() {{
    var s = window.getSelection();
    if (s.rangeCount) savedRange = s.getRangeAt(0);
  }}
  function restoreRange() {{
    if (!savedRange) return;
    var s = window.getSelection();
    s.removeAllRanges();
    s.addRange(savedRange);
  }}
  var imgBtn = document.getElementById('imgBtn');
  imgBtn.addEventListener('mousedown', function(e) {{ e.preventDefault(); saveRange(); }});
  imgBtn.addEventListener('click', function() {{ if (bridge) bridge.pickImage(); }});

  // --- inline image resize: click an image, drag its corner handle ---
  var imgSel = document.getElementById('imgSel');
  var imgHandle = document.getElementById('imgHandle');
  var selImg = null, dragging = false, startX = 0, startW = 0;
  function placeSel() {{
    if (!selImg || !doc.contains(selImg)) {{
      selImg = null; imgSel.style.display = 'none'; return;
    }}
    var r = selImg.getBoundingClientRect();
    imgSel.style.left = r.left + 'px';
    imgSel.style.top = r.top + 'px';
    imgSel.style.width = r.width + 'px';
    imgSel.style.height = r.height + 'px';
    imgSel.style.display = 'block';
  }}
  function selectImg(img) {{ selImg = img; placeSel(); }}
  function deselect() {{ selImg = null; imgSel.style.display = 'none'; }}
  doc.addEventListener('click', function(e) {{
    if (e.target && e.target.tagName === 'IMG') selectImg(e.target);
    else deselect();
  }});
  document.addEventListener('mousedown', function(e) {{
    if (e.target === imgHandle) return;
    if (e.target && e.target.tagName === 'IMG' && doc.contains(e.target)) return;
    if (!doc.contains(e.target)) deselect();
  }});
  imgHandle.addEventListener('mousedown', function(e) {{
    if (!selImg) return;
    e.preventDefault(); e.stopPropagation();
    dragging = true;
    startX = e.clientX;
    startW = selImg.getBoundingClientRect().width;
    document.addEventListener('mousemove', onImgDrag);
    document.addEventListener('mouseup', endImgDrag);
  }});
  function onImgDrag(e) {{
    if (!dragging || !selImg) return;
    var maxW = doc.clientWidth - 2;  // never wider than the page
    var w = Math.max(24, Math.min(startW + (e.clientX - startX), maxW));
    selImg.style.width = w + 'px';
    selImg.style.height = 'auto';   // lock aspect ratio
    selImg.style.maxWidth = '100%';
    placeSel();
  }}
  function endImgDrag() {{
    if (!dragging) return;
    dragging = false;
    document.removeEventListener('mousemove', onImgDrag);
    document.removeEventListener('mouseup', endImgDrag);
    notify();  // commit the new size to Python (save/export)
  }}
  document.getElementById('wrap').addEventListener('scroll', placeSel);
  window.addEventListener('resize', placeSel);

  doc.addEventListener('input', notify);
  new QWebChannel(qt.webChannelTransport, function(channel) {{
    bridge = channel.objects.bridge;
    // Only load-on-request; never auto-notify here (the doc is empty at load and
    // notifying would wipe pending content). Tell Python we are connected so it
    // can push any pending content now that this handler is wired up.
    bridge.requestContent.connect(function(html) {{ setDoc(html); }});
    bridge.requestDynamic.connect(function(json) {{ updateDynamic(JSON.parse(json)); }});
    bridge.insertImage.connect(function(uri) {{
      doc.focus(); restoreRange();
      document.execCommand('insertHTML', false,
        '<img style="max-width:100%; height:auto;" src="' + uri + '">');
      notify();
      // select the just-inserted image so its resize handle is ready
      var imgs = doc.querySelectorAll('img');
      for (var i = imgs.length - 1; i >= 0; i--) {{
        if (imgs[i].getAttribute('src') === uri) {{ selectImg(imgs[i]); break; }}
      }}
    }});
    bridge.onReady();
  }});
</script>
</body>
</html>"""


class _Bridge(QObject):
    """Python side of the QWebChannel bridge."""

    requestContent = Signal(str)  # Python -> JS: load this HTML into the document
    requestDynamic = Signal(str)  # Python -> JS: patch findings/sources (JSON)
    insertImage = Signal(str)  # Python -> JS: insert this data-URI image at the caret
    edited = Signal(str)  # JS -> Python: the document HTML changed
    ready = Signal()  # JS -> Python: the channel is connected
    imageRequested = Signal()  # JS -> Python: the user clicked "Insert image"

    @Slot(str)
    def onInput(self, html: str) -> None:  # noqa: N802 - called from JS
        self.edited.emit(html)

    @Slot()
    def onReady(self) -> None:  # noqa: N802 - called from JS
        self.ready.emit()

    @Slot()
    def pickImage(self) -> None:  # noqa: N802 - called from JS
        self.imageRequested.emit()


class ReportEditor(QWidget):
    """A rich-text report editor. ``content()`` is always the current HTML."""

    contentEdited = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._content = ""
        self._ready = False
        self._pending: str | None = None

        self._view = QWebEngineView()
        self._bridge = _Bridge()
        self._bridge.edited.connect(self._on_edited)
        # Readiness comes from the JS side (channel connected), not loadFinished:
        # emitting content before JS has wired up its handler would lose it.
        self._bridge.ready.connect(self._on_ready)
        self._bridge.imageRequested.connect(self._pick_image)
        self._channel = QWebChannel()
        self._channel.registerObject("bridge", self._bridge)
        self._view.page().setWebChannel(self._channel)
        page = _PAGE_TEMPLATE.format(qwebchannel=_qwebchannel_js())
        self._view.setHtml(page, QUrl("qrc:///"))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._view)

    def _on_ready(self) -> None:
        self._ready = True
        if self._pending is not None:
            self._bridge.requestContent.emit(self._pending)
            self._pending = None

    def _on_edited(self, html: str) -> None:
        self._content = html
        self.contentEdited.emit()

    def set_content(self, html: str) -> None:
        """Load HTML into the editor document."""
        self._content = html
        if self._ready:
            self._bridge.requestContent.emit(html)
        else:
            self._pending = html

    def content(self) -> str:
        """The current document HTML (kept in sync with every edit)."""
        return self._content

    def update_dynamic(self, parts: dict) -> None:
        """Refresh the findings/sources in place without touching analyst text."""
        if self._ready:
            self._bridge.requestDynamic.emit(json.dumps(parts))

    def _pick_image(self) -> None:
        """Let the analyst pick an image; embed it inline (data URI) at the caret."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Insert image",
            "",
            "Images (*.png *.jpg *.jpeg *.gif *.webp *.bmp)",
        )
        if not path:
            return
        data = Path(path).read_bytes()
        mime = mimetypes.guess_type(path)[0] or "image/png"
        uri = f"data:{mime};base64," + base64.b64encode(data).decode("ascii")
        self._bridge.insertImage.emit(uri)

    def scroll_to_anchor(self, name: str) -> None:
        """Scroll the document to an ``<a name=...>`` anchor (report section)."""
        js = f"var a=document.getElementsByName({json.dumps(name)})[0]; if(a) a.scrollIntoView();"
        self._view.page().runJavaScript(js)

    def print_pdf(self, path: Path | str, on_done=None) -> None:
        """Export the document to PDF via Chromium's print engine (high fidelity)."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if on_done is not None:
            self._view.page().pdfPrintingFinished.connect(
                lambda _p, ok: on_done(ok)
            )
        self._view.page().printToPdf(str(path))
