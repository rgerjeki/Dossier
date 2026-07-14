"""PySide6 (Qt) desktop entry point.

Qt is imported lazily inside ``main`` so that importing the engine, or running
the ``dossier`` console script without the ``ui`` extra, fails with a friendly
message instead of an import traceback.
"""

from __future__ import annotations

import os
import sys


def _ensure_qt_plugin_path() -> None:
    """Add PySide6's bundled plugins to Qt's library search path.

    PySide6's automatic plugin-path setup is occasionally unreliable, leaving the
    path empty so Qt cannot find its platform plugin ("Could not find the Qt
    platform plugin ... in ''") and aborts on launch. Adding the path via
    ``addLibraryPath`` (after QtCore is imported, so plugin dependencies resolve)
    is a safe fallback. It does not fix a genuinely broken install; a clean
    reinstall of PySide6 is the fix for that.
    """
    try:
        import PySide6
        from PySide6.QtCore import QCoreApplication
    except ImportError:
        return
    plugins = os.path.join(os.path.dirname(PySide6.__file__), "Qt", "plugins")
    if os.path.isdir(plugins) and plugins not in QCoreApplication.libraryPaths():
        QCoreApplication.addLibraryPath(plugins)


def main() -> int:
    try:
        from PySide6.QtCore import Qt, QTimer
        from PySide6.QtWidgets import QApplication
    except ImportError as err:
        raise SystemExit(
            "The desktop UI is not installed. Install it with:\n"
            '    pip install -e ".[ui]"'
        ) from err

    from .ui.window import MainWindow

    _ensure_qt_plugin_path()
    # Recommended for QtWebEngine (the report editor); must be set pre-QApplication.
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    # macOS: a Qt app launched from a terminal opens behind other windows and
    # does not take focus. Nudge it to the front so it is not "invisible".
    window.raise_()
    window.activateWindow()
    # Offer New/Open once the event loop is running and the window is up front,
    # so the (window-modal) prompt appears as a sheet and never hides behind it.
    # (The report editor is pre-warmed after this prompt closes; see prompt_startup.)
    QTimer.singleShot(0, window.prompt_startup)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
