"""Shared test setup.

The default suite runs Qt headless (offscreen). QtWebEngine (the report editor)
is only exercised by the opt-in web-editor tests (DOSSIER_WEBTEST=1), and its
setup (GPU/sandbox flags, the shared-GL attribute) is applied only then, since
those globals can destabilize the plain-Qt tests.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if os.environ.get("DOSSIER_WEBTEST") == "1":
    os.environ.setdefault(
        "QTWEBENGINE_CHROMIUM_FLAGS",
        "--disable-gpu --no-sandbox --single-process --disable-dev-shm-usage",
    )
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication

        QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    except Exception:  # pragma: no cover
        pass
