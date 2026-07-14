# PyInstaller spec for the Dossier standalone macOS app.
#
# Build (run from the repo root, with the venv active):
#   pyinstaller packaging/Dossier.spec --noconfirm \
#     --distpath <local-disk>/dist --workpath <local-disk>/build
#
# IMPORTANT: build AND run off a local disk, never a cloud-sync / File Provider
# folder (e.g. FileBox, iCloud Drive, Dropbox). Qt discovers its bundled plugins
# by enumerating a directory, and File Provider folders return an empty listing,
# so Qt aborts with "Could not find the Qt platform plugin cocoa". Ship the
# finished Dossier.app into /Applications.

import os

from PyInstaller.utils.hooks import collect_data_files

# maigret and holehe load bundled data files (their site databases) at runtime.
datas = collect_data_files("maigret") + collect_data_files("holehe")

# Qt modules Dossier never uses. QtWebEngine still needs QtQuick, QtQml,
# QtWebChannel, QtPositioning, QtOpenGL and QtNetwork, so those are NOT excluded.
_excluded_qt = [
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DInput",
    "PySide6.Qt3DAnimation", "PySide6.Qt3DExtras", "PySide6.Qt3DLogic",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtGraphs",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtSpatialAudio",
    "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtSensors",
    "PySide6.QtSerialPort", "PySide6.QtSerialBus", "PySide6.QtDesigner",
    "PySide6.QtHelp", "PySide6.QtUiTools", "PySide6.QtQuick3D",
    "PySide6.QtScxml", "PySide6.QtStateMachine", "PySide6.QtTextToSpeech",
    "PySide6.QtRemoteObjects", "PySide6.QtWebSockets", "PySide6.QtPdf",
    "PySide6.QtPdfWidgets", "PySide6.QtSql", "PySide6.QtTest",
]
# Build/dev-only packages that get pulled in transitively (mostly through maigret).
_excluded_dev = [
    "pytest", "_pytest", "pluggy", "ruff", "PyInstaller", "tkinter", "IPython",
]

a = Analysis(
    [os.path.join(SPECPATH, "dossier_app.py")],
    pathex=[],
    binaries=[],
    datas=datas,
    # Collectors are imported lazily inside the UI, so name them explicitly to be
    # sure their (and their deps') modules are analysed and bundled.
    hiddenimports=[
        "dossier.collectors.email",
        "dossier.collectors.usernames",
        "dossier.collectors.github",
        "dossier.collectors.keybase",
        "dossier.collectors.sec",
        "dossier.collectors.courtlistener",
        "dossier.collectors.searchkit",
        "dossier.collectors.metadata",
    ],
    excludes=_excluded_qt + _excluded_dev,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Dossier",
    debug=False,
    strip=False,
    upx=False,
    console=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Dossier")

app = BUNDLE(
    coll,
    name="Dossier.app",
    icon=None,  # TODO: add packaging/Dossier.icns
    bundle_identifier="org.dossier.app",
    info_plist={
        "CFBundleShortVersionString": "0.1.0",
        "CFBundleVersion": "0.1.0",
        "NSHighResolutionCapable": True,
        "LSApplicationCategoryType": "public.app-category.utilities",
    },
)
