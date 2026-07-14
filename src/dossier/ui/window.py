"""The main window: a collection view and a report view, with a menu and footer.

Layout follows the project mockups (in native window colors, not a custom theme):

- a menu bar (File / Edit / View / Collect / Report),
- a stacked central area with two views:
  - Collection: choose a collector, run it, and curate the findings table,
  - Report: a section-outline sidebar next to a live report preview,
- a footer status bar showing a running count and the last action.

Collection runs on a background thread so the UI never freezes during a sweep.
The collector is injectable so the window can be driven with a fake collector in
tests (no network, no Maigret).
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, QUrl, Signal
from PySide6.QtGui import (
    QAction,
    QDesktopServices,
    QFont,
    QKeySequence,
    QShortcut,
    QStandardItem,
    QStandardItemModel,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..case import Case, SubjectType, default_cases_dir, default_exports_dir
from ..collectors.base import Collector, CollectorRun
from ..models import Confidence, Finding

# Curation table columns.
COL_INCLUDE = 0
COL_STATUS = 1
COL_TYPE = 2
COL_VALUE = 3
COL_SOURCE = 4
COL_SRCCONF = 5
COL_ANALYST = 6
COL_NOTES = 7
_HEADERS = [
    "Include",
    "Status",
    "Type",
    "Value",
    "Source",
    "Source conf",
    "Analyst conf",
    "Notes",
]
_READONLY = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

# Collector choices (text-input collectors; metadata has its own file action).
CHOICE_USERNAME = "Username (Maigret)"
CHOICE_GITHUB = "GitHub (username)"
CHOICE_KEYBASE = "Keybase (username)"
CHOICE_EMAIL = "Email (Gravatar + holehe)"
CHOICE_SEC = "SEC EDGAR (name/company)"
CHOICE_COURT = "CourtListener (name/entity)"
CHOICE_SEARCHKIT = "Search-kit links"
# The dropdown is grouped under section headers; niche collectors sit apart.
_COLLECTOR_GROUPS: list[tuple[str, list[str]]] = [
    ("People & accounts", [CHOICE_USERNAME, CHOICE_GITHUB, CHOICE_EMAIL]),
    ("Business & legal", [CHOICE_SEC, CHOICE_COURT]),
    ("Guided links", [CHOICE_SEARCHKIT]),
    ("Specialized", [CHOICE_KEYBASE]),
]
_COLLECTOR_CHOICES = [c for _, choices in _COLLECTOR_GROUPS for c in choices]
_PLACEHOLDERS = {
    CHOICE_USERNAME: "Username to search",
    CHOICE_GITHUB: "GitHub username",
    CHOICE_KEYBASE: "Keybase username",
    CHOICE_EMAIL: "Email address",
    CHOICE_SEC: "Name or company",
    CHOICE_COURT: "Name or entity",
    CHOICE_SEARCHKIT: "Username, name, email, image URL, or domain",
}
_CHOICE_SUBJECT_TYPE = {
    CHOICE_USERNAME: SubjectType.USERNAME,
    CHOICE_GITHUB: SubjectType.USERNAME,
    CHOICE_KEYBASE: SubjectType.USERNAME,
    CHOICE_EMAIL: SubjectType.EMAIL,
    CHOICE_SEC: SubjectType.NAME,
    CHOICE_COURT: SubjectType.NAME,
    CHOICE_SEARCHKIT: SubjectType.NAME,
}
# Enrichment: a finding (e.g. a Maigret GitHub hit) can be turned into real data
# by running a data collector on it. This maps a GitHub profile URL to a username.
_GITHUB_URL = re.compile(r"github\.com/([A-Za-z0-9](?:[A-Za-z0-9-]{0,38})?)/?$")
_GITHUB_RESERVED = {"orgs", "about", "search", "sponsors", "features", "topics", "settings"}


def _github_username(finding: Finding) -> str | None:
    """The GitHub username a finding can be enriched with (else None)."""
    if finding.source.startswith("GitHub"):  # already the GitHub collector's output
        return None
    match = _GITHUB_URL.search(finding.source_url or "")
    if not match or match.group(1).lower() in _GITHUB_RESERVED:
        return None
    return match.group(1)


# Which collector to pre-select for a case's subject type (file uses the button).
_SUBJECT_TYPE_CHOICE = {
    SubjectType.USERNAME: CHOICE_USERNAME,
    SubjectType.EMAIL: CHOICE_EMAIL,
    SubjectType.NAME: CHOICE_SEARCHKIT,
}

_VIEW_COLLECTION = 0
_VIEW_REPORT = 1


_FINDING_ROLE = Qt.ItemDataRole.UserRole  # stores the Finding on a row's item


class NewCaseDialog(QDialog):
    """Collects the details for a new case (name required, the rest optional)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("New Case")
        # Window-modal so macOS shows it as a sheet on the parent window (it cannot
        # hide behind the main window and block input invisibly).
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self._name = QLineEdit()
        self._name.setPlaceholderText("A name for this case (required)")
        self._subject = QLineEdit()
        self._subject.setPlaceholderText("Username, email, or name being investigated")
        self._subject_type = QComboBox()
        self._subject_type.addItems([t.value for t in SubjectType])
        self._template = QComboBox()
        from ..report.templates import TEMPLATES

        for key, tmpl in TEMPLATES.items():
            self._template.addItem(tmpl.name, key)
            self._template.setItemData(
                self._template.count() - 1, tmpl.description, Qt.ItemDataRole.ToolTipRole
            )
        self._analyst = QLineEdit()
        self._scope = QLineEdit()
        self._scope.setPlaceholderText("Scope and consent, e.g. safe target, public passive only")
        self._authorized = QCheckBox("Authorized: public, lawful, passive data only")

        form = QFormLayout(self)
        form.addRow("Case name", self._name)
        form.addRow("Subject", self._subject)
        form.addRow("Subject type", self._subject_type)
        form.addRow("Report template", self._template)
        form.addRow("Investigator", self._analyst)
        form.addRow("Scope / consent", self._scope)
        form.addRow("", self._authorized)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _on_accept(self) -> None:
        if not self._name.text().strip():
            self._name.setFocus()
            return
        self.accept()

    def build_case(self) -> Case:
        name = self._name.text().strip()
        return Case(
            title=name,
            subject=self._subject.text().strip() or name,
            subject_type=SubjectType(self._subject_type.currentText()),
            template=self._template.currentData(),
            analyst=self._analyst.text().strip(),
            scope_note=self._scope.text().strip(),
            authorized=self._authorized.isChecked(),
        )


class _WorkerSignals(QObject):
    done = Signal(object)  # emits a CollectorRun


class _CollectorWorker(QRunnable):
    """Runs one collector off the UI thread. The collector handles its own errors
    and always returns a CollectorRun, so ``run`` does not need a try/except."""

    def __init__(self, collector: Collector, target: str) -> None:
        super().__init__()
        self.collector = collector
        self.target = target
        self.signals = _WorkerSignals()

    def run(self) -> None:  # noqa: D401 - Qt entry point
        self.signals.done.emit(self.collector.collect(self.target))


class MainWindow(QMainWindow):
    """Dossier workbench: collect and curate, then preview and export a report."""

    def __init__(
        self, collector: Collector | None = None, report_editor_factory=None
    ) -> None:
        super().__init__()
        self._collector = collector  # injected collector wins (tests)
        # Factory for the report editor; tests inject a lightweight fake so the
        # suite does not spin up QtWebEngine (Chromium).
        self._report_editor_factory = report_editor_factory
        self._pool = QThreadPool.globalInstance()
        self._case: Case | None = None
        self._case_path: str | None = None  # file the case is saved to
        self._dirty = False  # unsaved changes
        self._rows: list[Finding] = []
        self._loading = False
        # Whether the report editor has been populated for the current case. The
        # findings tables then update live on curation; analyst text is preserved.
        self._report_initialized = False

        self.setWindowTitle("Dossier")
        self.resize(1080, 660)

        # Auto-save periodically so nothing is lost on a crash or an unclean exit.
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(30_000)
        self._autosave_timer.timeout.connect(self._autosave)
        self._autosave_timer.start()

        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_collection_view())
        self._stack.addWidget(self._build_report_view())

        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_navbar())
        outer.addWidget(self._stack, stretch=1)
        self.setCentralWidget(central)

        self._build_menu()
        self._build_statusbar()
        self.show_collection_view()
        self._refresh_info()

    def _build_navbar(self) -> QWidget:
        # A deterministic, left-aligned nav bar (native tab widgets center their
        # tabs on macOS). View buttons on the left, case actions on the right.
        self._btn_collection = QPushButton("Collection")
        self._btn_report = QPushButton("Report")
        group = QButtonGroup(self)
        for index, button in enumerate((self._btn_collection, self._btn_report)):
            button.setCheckable(True)
            button.setMinimumWidth(96)
            group.addButton(button, index)
        self._btn_collection.setChecked(True)
        self._btn_collection.clicked.connect(self.show_collection_view)
        self._btn_report.clicked.connect(self.show_report_view)

        new_button = QPushButton("New")
        new_button.setToolTip("Start a new case")
        new_button.clicked.connect(self.new_case)
        open_button = QPushButton("Open")
        open_button.setToolTip("Open a saved case")
        open_button.clicked.connect(lambda: self.open_case())
        save_button = QPushButton("Save")
        save_button.setToolTip("Save the current case")
        save_button.clicked.connect(lambda: self.save_case())

        row = QHBoxLayout()
        row.setContentsMargins(10, 8, 10, 8)
        row.setSpacing(6)
        row.addWidget(self._btn_collection)
        row.addWidget(self._btn_report)
        row.addStretch(1)
        row.addWidget(new_button)
        row.addWidget(open_button)
        row.addWidget(save_button)

        bar = QWidget()
        bar.setLayout(row)

        holder = QWidget()
        holder_layout = QVBoxLayout(holder)
        holder_layout.setContentsMargins(0, 0, 0, 0)
        holder_layout.setSpacing(0)
        holder_layout.addWidget(bar)
        rule = QFrame()
        rule.setFrameShape(QFrame.Shape.HLine)
        rule.setFrameShadow(QFrame.Shadow.Sunken)
        holder_layout.addWidget(rule)
        return holder

    # --- construction ---------------------------------------------------------

    def _build_collection_view(self) -> QWidget:
        self._input = QLineEdit()
        self._input.setPlaceholderText(_PLACEHOLDERS[CHOICE_USERNAME])
        self._input.returnPressed.connect(self.run_collection)

        # Grouped dropdown: bold, non-selectable section headers over the choices.
        self._choice = QComboBox()
        model = QStandardItemModel(self._choice)
        for header, choices in _COLLECTOR_GROUPS:
            head_item = QStandardItem(header)
            head_item.setFlags(Qt.ItemFlag.NoItemFlags)
            head_font = head_item.font()
            head_font.setBold(True)
            head_item.setFont(head_font)
            model.appendRow(head_item)
            for choice in choices:
                model.appendRow(QStandardItem(choice))
        self._choice.setModel(model)
        self._choice.setCurrentText(CHOICE_USERNAME)  # first real choice
        self._choice.currentTextChanged.connect(self._on_choice_changed)

        self._run_button = QPushButton("Run")
        self._run_button.clicked.connect(self.run_collection)
        file_button = QPushButton("Metadata from file...")
        file_button.clicked.connect(self.add_file)

        self._filter = QLineEdit()
        self._filter.setPlaceholderText("Filter findings...")
        self._filter.setClearButtonEnabled(True)
        self._filter.setMaximumWidth(220)
        self._filter.textChanged.connect(self._apply_filter)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Collector"))
        controls.addWidget(self._choice)
        controls.addWidget(self._input, stretch=1)
        controls.addWidget(self._run_button)
        controls.addWidget(file_button)
        controls.addSpacing(12)
        controls.addWidget(self._filter)

        self._table = QTableWidget(0, len(_HEADERS))
        self._table.setHorizontalHeaderLabels(_HEADERS)
        self._table.setAlternatingRowColors(True)
        self._table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._table.verticalHeader().setVisible(False)
        # Qt's built-in sorting conflicts with the always-visible dropdown widgets
        # in the Analyst column, so we sort manually on header click and re-render
        # (which keeps the dropdowns correct). Columns stay resizable + filterable.
        self._table.setSortingEnabled(False)
        self._sort_col: int | None = None
        self._sort_asc = True
        head = self._table.horizontalHeader()
        head.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        head.setStretchLastSection(True)
        head.setSectionsClickable(True)
        head.sectionClicked.connect(self._on_header_clicked)
        for col, width in (
            (COL_INCLUDE, 64),
            (COL_STATUS, 96),
            (COL_TYPE, 76),
            (COL_VALUE, 280),
            (COL_SOURCE, 150),
            (COL_SRCCONF, 92),
            (COL_ANALYST, 96),
        ):
            self._table.setColumnWidth(col, width)
        self._table.itemChanged.connect(self._on_item_changed)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._show_table_menu)
        self._table.doubleClicked.connect(self._on_double_click)
        QShortcut(QKeySequence.StandardKey.Copy, self._table, self._copy_selection)
        QShortcut(QKeySequence.StandardKey.Delete, self._table, self.delete_selected_findings)

        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.addLayout(controls)
        layout.addWidget(self._table, stretch=1)
        page = QWidget()
        page.setLayout(layout)
        return page

    def _build_report_view(self) -> QWidget:
        from ..report.templates import TEMPLATES

        self._template = QComboBox()
        for key, tmpl in TEMPLATES.items():
            self._template.addItem(tmpl.name, key)
            self._template.setItemData(
                self._template.count() - 1, tmpl.description, Qt.ItemDataRole.ToolTipRole
            )
        self._template.currentIndexChanged.connect(self._on_template_changed)

        docx_button = QPushButton("Export Word")
        docx_button.clicked.connect(lambda: self.export_docx())
        pdf_button = QPushButton("Export PDF")
        pdf_button.clicked.connect(lambda: self.export_pdf())

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Template"))
        controls.addWidget(self._template)
        controls.addStretch(1)
        controls.addWidget(docx_button)
        controls.addWidget(pdf_button)

        self._outline = QListWidget()
        self._outline.itemClicked.connect(self._on_outline_clicked)

        side = QWidget()
        side.setMaximumWidth(230)
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.addWidget(QLabel("Sections"))
        side_layout.addWidget(self._outline, stretch=1)

        # The report is a real editable document (QtWebEngine contenteditable with
        # its own formatting toolbar). Created lazily on first use so the
        # collection workflow never spins up Chromium.
        self._editor = None
        self._editor_container = QWidget()
        self._editor_layout = QVBoxLayout(self._editor_container)
        self._editor_layout.setContentsMargins(0, 0, 0, 0)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(side)
        split.addWidget(self._editor_container)
        split.setStretchFactor(1, 1)

        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.addLayout(controls)
        layout.addWidget(split, stretch=1)
        page = QWidget()
        page.setLayout(layout)
        return page

    def prewarm_report_editor(self) -> None:
        """Create the report editor ahead of time (background warm-up).

        The web editor's engine (Chromium) is slow to start, so building it just
        after launch, while the user is on the collection view, makes the Report
        tab open instantly instead of stalling on first click.
        """
        self._report_editor()

    def _report_editor(self):
        """Create the report editor on first use (lazy)."""
        if self._editor is None:
            if self._report_editor_factory is not None:
                self._editor = self._report_editor_factory()
            else:
                from .report_editor import ReportEditor

                self._editor = ReportEditor()
            self._editor.contentEdited.connect(self._on_report_edited)
            self._editor_layout.addWidget(self._editor)
        return self._editor

    def _build_menu(self) -> None:
        bar = self.menuBar()

        file_menu = bar.addMenu("File")
        self._add_action(file_menu, "New Case...", self.new_case, "Ctrl+N")
        self._add_action(file_menu, "Open Case...", lambda: self.open_case(), "Ctrl+O")
        self._add_action(file_menu, "Save Case", lambda: self.save_case(), "Ctrl+S")
        self._add_action(file_menu, "Save Case As...", self.save_case_as, "Ctrl+Shift+S")
        file_menu.addSeparator()
        self._add_action(file_menu, "Export Word...", lambda: self.export_docx())
        self._add_action(file_menu, "Export PDF...", lambda: self.export_pdf())
        file_menu.addSeparator()
        self._add_action(file_menu, "Quit", self.close, "Ctrl+Q")

        edit_menu = bar.addMenu("Edit")
        self._add_action(edit_menu, "Include All", lambda: self._set_all_included(True))
        self._add_action(edit_menu, "Exclude All", lambda: self._set_all_included(False))
        edit_menu.addSeparator()
        self._add_action(edit_menu, "Delete Selected Findings", self.delete_selected_findings)
        self._add_action(edit_menu, "Remove Excluded Findings", self.remove_excluded_findings)

        view_menu = bar.addMenu("View")
        self._add_action(view_menu, "Collection", self.show_collection_view)
        self._add_action(view_menu, "Report", self.show_report_view)

        collect_menu = bar.addMenu("Collect")
        self._add_action(collect_menu, "Run Collector", self.run_collection, "Ctrl+R")
        self._add_action(collect_menu, "Metadata from File...", self.add_file)

        report_menu = bar.addMenu("Report")
        self._add_action(report_menu, "Show Report View", self.show_report_view)
        self._add_action(report_menu, "Export Word...", lambda: self.export_docx())
        self._add_action(report_menu, "Export PDF...", lambda: self.export_pdf())

    def _add_action(self, menu, text, slot, shortcut: str | None = None) -> QAction:
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(shortcut)
        action.triggered.connect(slot)
        menu.addAction(action)
        return action

    def _build_statusbar(self) -> None:
        self._status = QLabel("Enter a value and press Run.")
        self._info = QLabel("No case open.")
        self._info.setFont(QFont("Menlo"))
        self._info.setStyleSheet("color: #6b6a64;")
        self.statusBar().addWidget(self._status, 1)
        self.statusBar().addPermanentWidget(self._info)

    # --- view switching -------------------------------------------------------

    def show_collection_view(self) -> None:
        self._stack.setCurrentIndex(_VIEW_COLLECTION)
        self._btn_collection.setChecked(True)

    def show_report_view(self) -> None:
        self._refresh_report()
        self._stack.setCurrentIndex(_VIEW_REPORT)
        self._btn_report.setChecked(True)

    def preview_report(self) -> None:
        """Kept for compatibility: switch to the embedded report view."""
        self.show_report_view()

    def _refresh_report(self) -> None:
        from ..report.render import render_html, report_outline

        self._outline.clear()
        if self._case is None:
            self._report_editor().set_content("<p><i>No case open.</i></p>")
            return
        self._sync_template_combo()
        for title, anchor in report_outline(self._case):
            item = QListWidgetItem(title)
            item.setData(Qt.ItemDataRole.UserRole, anchor)
            self._outline.addItem(item)
        if not self._report_initialized:
            # Populate the document once: the saved edited version if there is one,
            # else a fresh render. After this, curation patches only the findings.
            self._report_editor().set_content(
                self._case.report_html or render_html(self._case)
            )
            self._report_initialized = True
        else:
            self._update_report_dynamic()

    def _sync_template_combo(self) -> None:
        """Point the toolbar combo at the current case's template (no signal)."""
        if self._case is None:
            return
        idx = self._template.findData(self._case.template)
        if idx < 0:
            idx = 0
        self._template.blockSignals(True)
        self._template.setCurrentIndex(idx)
        self._template.blockSignals(False)

    def _on_template_changed(self, index: int) -> None:
        """Switch the case's report template from the toolbar combo.

        The outline (section structure) changes, so the report is rebuilt from the
        new template. That discards analyst edits to the *report document*, so if
        there are any, confirm first. The collected findings are never touched.
        """
        if self._case is None:
            return
        key = self._template.itemData(index)
        if not key or key == self._case.template:
            return
        if self._case.report_html:
            reply = self._question(
                "Change template?",
                "Switching templates rebuilds the report layout and discards your "
                "current report edits. The collected findings are kept. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                self._sync_template_combo()  # revert the combo to the real template
                return
        self._case.template = key
        self._case.report_html = ""  # structure changed; rebuild from the new outline
        self._report_initialized = False
        self._case.touch()
        self._mark_dirty()
        self._refresh_report()

    def _update_report_dynamic(self) -> None:
        """Refresh the report's findings tables/sources from current curation.

        Analyst text elsewhere in the document is left untouched.
        """
        if self._editor is None or self._case is None or not self._report_initialized:
            return
        from ..report.render import render_dynamic_parts

        self._editor.update_dynamic(render_dynamic_parts(self._case))

    def _on_report_edited(self) -> None:
        if self._case is None:
            return
        self._case.report_html = self._report_editor().content()
        self._mark_dirty()

    def _on_outline_clicked(self, item: QListWidgetItem) -> None:
        anchor = item.data(Qt.ItemDataRole.UserRole)
        if anchor:
            self._report_editor().scroll_to_anchor(anchor)

    # --- collection -----------------------------------------------------------

    def _on_choice_changed(self, text: str) -> None:
        self._input.setPlaceholderText(_PLACEHOLDERS.get(text, ""))

    def _get_collector(self) -> Collector:
        if self._collector is not None:
            return self._collector
        choice = self._choice.currentText()
        if choice == CHOICE_GITHUB:
            from ..collectors.github import GitHubCollector

            return GitHubCollector()
        if choice == CHOICE_KEYBASE:
            from ..collectors.keybase import KeybaseCollector

            return KeybaseCollector()
        if choice == CHOICE_EMAIL:
            from ..collectors.email import EmailCollector

            return EmailCollector()
        if choice == CHOICE_SEC:
            from ..collectors.sec import SECCollector

            return SECCollector()
        if choice == CHOICE_COURT:
            from ..collectors.courtlistener import CourtListenerCollector

            return CourtListenerCollector()
        if choice == CHOICE_SEARCHKIT:
            from ..collectors.searchkit import SearchKitCollector

            return SearchKitCollector()
        from ..collectors.usernames import MaigretCollector

        return MaigretCollector()

    def run_collection(self) -> None:
        target = self._input.text().strip()
        if not target:
            self._status.setText("Enter a value first.")
            return
        subject_type = _CHOICE_SUBJECT_TYPE.get(
            self._choice.currentText(), SubjectType.USERNAME
        )
        self._run_collector(self._get_collector(), target, subject_type)

    def add_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select a file to read metadata from", "", "All files (*)"
        )
        if not path:
            return
        from ..collectors.metadata import MetadataCollector

        self._run_collector(MetadataCollector(), path, SubjectType.FILE)

    def _run_collector(
        self, collector: Collector, target: str, subject_type: SubjectType
    ) -> None:
        self._ensure_case(subject_type)
        self._run_button.setEnabled(False)
        self._status.setText(f"Running {collector.name} on '{target}'...")

        worker = _CollectorWorker(collector, target)
        worker.signals.done.connect(self._on_done)
        self._pool.start(worker)

    def _on_done(self, run: CollectorRun) -> None:
        self._ensure_case(SubjectType.USERNAME)
        self._case.findings.extend(run.findings)
        self._mark_dirty()
        self._render_case()
        self._update_report_dynamic()
        prefix = "" if run.ok else "Note: "
        message = f"{prefix}{run.message}"
        if any(_github_username(f) for f in run.findings):
            message += "  ·  right-click a GitHub result to fetch its full profile"
        self._status.setText(message)
        self._run_button.setEnabled(True)

    def _ensure_case(self, subject_type: SubjectType = SubjectType.USERNAME) -> None:
        if self._case is None:
            subject = self._input.text().strip() or "unknown"
            self._case = Case(subject=subject, subject_type=subject_type)

    # --- case management ------------------------------------------------------

    def _mark_dirty(self) -> None:
        if self._case is not None:
            self._case.touch()
            self._dirty = True

    def _autosave(self) -> None:
        """Persist the case periodically so nothing is lost on a crash/unclean exit."""
        if self._case is None or not self._dirty:
            return
        path = self._case_path or str(default_cases_dir() / self._case.filename())
        try:
            self._case.write(path)
        except OSError:
            return  # keep dirty; try again next tick
        self._case_path = path
        self._dirty = False
        self._status.setText(f"Auto-saved {datetime.now().strftime('%H:%M:%S')}")

    def _set_case(self, case: Case, path: str | None, dirty: bool) -> None:
        self._case = case
        self._case_path = path
        self._dirty = dirty
        # The report editor is repopulated for the new case on next report view.
        self._report_initialized = False
        self._input.setText(case.subject)
        # Pre-select the collector that matches the case's subject type.
        choice = _SUBJECT_TYPE_CHOICE.get(case.subject_type)
        if choice:
            self._choice.setCurrentText(choice)
        elif case.subject_type is SubjectType.FILE:
            self._status.setText("File subject: use 'Metadata from file...' to collect.")
        self._render_case()
        self._refresh_info()
        # Keep the report in sync when a case is loaded while the report tab is open.
        if self._stack.currentIndex() == _VIEW_REPORT:
            self._refresh_report()

    def _question(self, title: str, text: str, buttons, default) -> object:
        # Window-modal so it appears as a sheet on macOS (never hidden behind the
        # main window). Static QMessageBox.question is app-modal and can hide.
        box = QMessageBox(self)
        box.setWindowModality(Qt.WindowModality.WindowModal)
        box.setWindowTitle(title)
        box.setText(text)
        box.setStandardButtons(buttons)
        box.setDefaultButton(default)
        self.raise_()
        self.activateWindow()
        box.exec()
        return box.standardButton(box.clickedButton())

    def _maybe_save_current(self) -> bool:
        """Offer to save unsaved changes. Return True to proceed, False to cancel."""
        if self._case is None or not self._dirty:
            return True
        reply = self._question(
            "Save changes?",
            "You have unsaved changes. Save before continuing?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if reply == QMessageBox.StandardButton.Cancel:
            return False
        if reply == QMessageBox.StandardButton.Save:
            return self.save_case()
        return True  # Discard

    def create_case(self, case: Case, path: str | None = None) -> None:
        """Adopt a new case, saving it to ``path`` if given. Dialog-free (testable)."""
        if path:
            case.write(path)
        self._set_case(case, path=path, dirty=path is None)
        if path:
            self._status.setText(f"Created case, saved to {path}")
        else:
            self._status.setText("Created case (not yet saved).")

    def new_case(self) -> None:
        if not self._maybe_save_current():
            return
        dialog = NewCaseDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        case = dialog.build_case()
        suggested = str(default_cases_dir() / case.filename())
        path, _ = QFileDialog.getSaveFileName(
            self, "Save new case as", suggested, "Case files (*.json)"
        )
        if not path:
            return  # choosing a location is part of creating the case
        self.create_case(case, path)

    def save_case(self, path: str | None = None) -> bool:
        """Save to the current file (or prompt for a location on first save)."""
        if self._case is None:
            self._status.setText("No case to save.")
            return False
        target = path or self._case_path
        if target is None:
            return self.save_case_as()
        self._case.write(target)
        self._case_path = target
        self._dirty = False
        self._status.setText(f"Saved case to {target}")
        return True

    def save_case_as(self) -> bool:
        """Choose a new location and save the case there."""
        if self._case is None:
            self._status.setText("No case to save.")
            return False
        suggested = self._case_path or str(default_cases_dir() / self._case.filename())
        path, _ = QFileDialog.getSaveFileName(
            self, "Save case as", suggested, "Case files (*.json)"
        )
        if not path:
            return False
        return self.save_case(path)

    def open_case(self, path: str | None = None) -> None:
        if not self._maybe_save_current():
            return
        if path is None:
            path, _ = QFileDialog.getOpenFileName(
                self, "Open case", str(default_cases_dir()), "Case files (*.json)"
            )
            if not path:
                return
        self._set_case(Case.load(path), path=path, dirty=False)
        self._status.setText(f"Opened case from {Path(path).name}")

    def prompt_startup(self) -> None:
        """On launch with no case, offer to create a new one or open an existing one."""
        if self._case is not None:
            return
        box = QMessageBox(self)
        box.setWindowModality(Qt.WindowModality.WindowModal)  # a sheet on macOS
        box.setWindowTitle("Dossier")
        box.setText("Start a new case, or open an existing one?")
        new_btn = box.addButton("New Case", QMessageBox.ButtonRole.AcceptRole)
        open_btn = box.addButton("Open Case", QMessageBox.ButtonRole.ActionRole)
        box.addButton("Later", QMessageBox.ButtonRole.RejectRole)
        self.raise_()
        self.activateWindow()
        box.exec()
        clicked = box.clickedButton()
        if clicked == new_btn:
            self.new_case()
        elif clicked == open_btn:
            self.open_case()
        # Pre-warm the report editor only now that the startup prompt (and any
        # New/Open dialog) has closed. Creating the browser engine while a modal
        # is open would dismiss it.
        QTimer.singleShot(400, self.prewarm_report_editor)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        if not self._maybe_save_current():
            event.ignore()
            return
        event.accept()

    # --- report export --------------------------------------------------------

    def _export_basename(self) -> str:
        return self._case.filename().removesuffix(".json")

    def export_docx(self, path: str | None = None) -> None:
        if self._case is None:
            self._status.setText("No case to export.")
            return
        if path is None:
            suggested = str(default_exports_dir() / f"{self._export_basename()}.docx")
            path, _ = QFileDialog.getSaveFileName(
                self, "Export Word report", suggested, "Word documents (*.docx)"
            )
            if not path:
                return
        from .export import html_to_docx

        html_to_docx(self._report_html(), path)
        self._status.setText(f"Exported Word report to {path}")

    def export_pdf(self, path: str | None = None) -> None:
        if self._case is None:
            self._status.setText("No case to export.")
            return
        if path is None:
            suggested = str(default_exports_dir() / f"{self._export_basename()}.pdf")
            path, _ = QFileDialog.getSaveFileName(
                self, "Export PDF report", suggested, "PDF documents (*.pdf)"
            )
            if not path:
                return
        # Chromium renders the PDF (high fidelity); the finish is asynchronous.
        self._report_editor().print_pdf(
            path, lambda ok: self._status.setText(
                f"Exported PDF report to {path}" if ok else "PDF export failed."
            )
        )

    def _report_html(self) -> str:
        # The current report document: the analyst's edits if present, else a
        # freshly generated draft.
        from ..report.render import render_html

        if self._editor is not None and self._editor.content().strip():
            return self._editor.content()
        return self._case.report_html or render_html(self._case)

    # --- curation table -------------------------------------------------------

    def _render_case(self) -> None:
        findings = list(self._case.findings) if self._case else []
        if self._sort_col is not None:
            findings.sort(
                key=lambda f: self._sort_key(f, self._sort_col),
                reverse=not self._sort_asc,
            )
        self._rows = findings
        self._loading = True
        self._table.setRowCount(len(findings))
        for row, finding in enumerate(findings):
            include = QTableWidgetItem()
            include.setFlags(_READONLY | Qt.ItemFlag.ItemIsUserCheckable)
            include.setCheckState(
                Qt.CheckState.Checked if finding.included else Qt.CheckState.Unchecked
            )
            include.setData(_FINDING_ROLE, finding)
            self._table.setItem(row, COL_INCLUDE, include)

            for col, text in (
                (COL_STATUS, finding.status.value),
                (COL_TYPE, finding.type.value),
                (COL_VALUE, finding.value),
                (COL_SOURCE, finding.source),
                (COL_SRCCONF, finding.source_confidence.value),
            ):
                item = QTableWidgetItem(text)
                item.setFlags(_READONLY)
                self._table.setItem(row, col, item)

            # Always-visible dropdown for the analyst confidence.
            self._table.setCellWidget(row, COL_ANALYST, self._analyst_combo(finding))

            notes = QTableWidgetItem(finding.notes)
            notes.setFlags(_READONLY | Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(row, COL_NOTES, notes)

        self._loading = False
        self._apply_filter(self._filter.text())
        self._refresh_info()

    def _analyst_combo(self, finding: Finding) -> QComboBox:
        combo = QComboBox()
        for level in Confidence:
            combo.addItem(level.value)
        combo.setCurrentText(finding.analyst_confidence.value)
        combo.currentTextChanged.connect(
            lambda text, f=finding: self._set_analyst(f, text)
        )
        return combo

    def _set_analyst(self, finding: Finding, text: str) -> None:
        finding.analyst_confidence = Confidence(text)
        self._mark_dirty()
        self._update_report_dynamic()

    def _finding_for_row(self, row: int) -> Finding | None:
        item = self._table.item(row, COL_INCLUDE)
        return item.data(_FINDING_ROLE) if item else None

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._loading:
            return
        finding = self._finding_for_row(item.row())
        if finding is None:
            return
        if item.column() == COL_INCLUDE:
            finding.included = item.checkState() == Qt.CheckState.Checked
        elif item.column() == COL_NOTES:
            finding.notes = item.text()
        if self._case:
            self._mark_dirty()
        self._refresh_info()
        self._update_report_dynamic()

    def _set_all_included(self, included: bool) -> None:
        if self._case is None:
            return
        self._loading = True
        state = Qt.CheckState.Checked if included else Qt.CheckState.Unchecked
        for row in range(self._table.rowCount()):
            finding = self._finding_for_row(row)
            if finding is not None:
                finding.included = included
            self._table.item(row, COL_INCLUDE).setCheckState(state)
        self._loading = False
        self._mark_dirty()
        self._refresh_info()
        self._update_report_dynamic()

    # --- deleting findings (cleaning up the table) ---------------------------

    def _selected_findings(self) -> list[Finding]:
        rows = sorted({i.row() for i in self._table.selectedItems()})
        return [f for r in rows if (f := self._finding_for_row(r)) is not None]

    def _remove_findings(self, findings: list[Finding]) -> None:
        """Permanently remove findings from the case (no confirm; testable core)."""
        if self._case is None or not findings:
            return
        ids = {f.id for f in findings}
        self._case.findings = [f for f in self._case.findings if f.id not in ids]
        self._mark_dirty()
        self._render_case()
        self._update_report_dynamic()
        self._status.setText(f"Deleted {len(findings)} finding(s).")

    def _delete_with_confirm(self, findings: list[Finding], descriptor: str = "finding(s)") -> None:
        if not findings or self._case is None:
            return
        reply = self._question(
            "Delete findings?",
            f"Delete {len(findings)} {descriptor}? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._remove_findings(findings)

    def delete_selected_findings(self) -> None:
        self._delete_with_confirm(self._selected_findings())

    def remove_excluded_findings(self) -> None:
        if self._case is None:
            self._status.setText("No case open.")
            return
        excluded = [f for f in self._case.findings if not f.included]
        if not excluded:
            self._status.setText("No excluded findings to remove.")
            return
        self._delete_with_confirm(excluded, "excluded finding(s)")

    def _sort_key(self, finding: Finding, col: int):
        return {
            COL_INCLUDE: (0 if finding.included else 1),
            COL_STATUS: finding.status.value,
            COL_TYPE: finding.type.value,
            COL_VALUE: finding.value.lower(),
            COL_SOURCE: finding.source.lower(),
            COL_SRCCONF: finding.source_confidence.value,
            COL_ANALYST: finding.analyst_confidence.value,
            COL_NOTES: finding.notes.lower(),
        }.get(col, "")

    def _on_header_clicked(self, col: int) -> None:
        """Sort the findings by the clicked column (toggling direction)."""
        if self._case is None:
            return
        if self._sort_col == col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col
            self._sort_asc = True
        header = self._table.horizontalHeader()
        header.setSortIndicatorShown(True)
        header.setSortIndicator(
            col,
            Qt.SortOrder.AscendingOrder if self._sort_asc else Qt.SortOrder.DescendingOrder,
        )
        self._render_case()

    # --- table interaction: filter, copy, open -------------------------------

    def _apply_filter(self, text: str) -> None:
        needle = text.strip().lower()
        for row in range(self._table.rowCount()):
            haystack = " ".join(
                self._table.item(row, col).text()
                for col in range(self._table.columnCount())
                if self._table.item(row, col)
            ).lower()
            self._table.setRowHidden(row, bool(needle) and needle not in haystack)

    def _copy_selection(self) -> None:
        items = self._table.selectedItems()
        if not items:
            return
        rows = sorted({i.row() for i in items})
        cols = sorted({i.column() for i in items})
        lines = []
        for row in rows:
            cells = []
            for col in cols:
                item = self._table.item(row, col)
                cells.append(item.text() if item and item.column() in cols else "")
            lines.append("\t".join(cells))
        QApplication.clipboard().setText("\n".join(lines))

    def _on_double_click(self, index) -> None:
        # Double-clicking a Value or Source cell opens its link, if any.
        if index.column() in (COL_VALUE, COL_SOURCE):
            finding = self._finding_for_row(index.row())
            if finding and finding.source_url:
                QDesktopServices.openUrl(QUrl(finding.source_url))

    def _show_table_menu(self, pos) -> None:
        item = self._table.itemAt(pos)
        if item is None:
            return
        finding = self._finding_for_row(item.row())
        menu = QMenu(self._table)
        if finding and finding.source_url:
            open_action = menu.addAction("Open link in browser")
            open_action.triggered.connect(
                lambda: QDesktopServices.openUrl(QUrl(finding.source_url))
            )
            copy_url = menu.addAction("Copy source URL")
            copy_url.triggered.connect(
                lambda: QApplication.clipboard().setText(finding.source_url)
            )
        copy_cell = menu.addAction("Copy cell")
        copy_cell.triggered.connect(
            lambda: QApplication.clipboard().setText(item.text())
        )
        if finding:
            copy_value = menu.addAction("Copy value")
            copy_value.triggered.connect(
                lambda: QApplication.clipboard().setText(finding.value)
            )
            username = _github_username(finding)
            if username:
                menu.addSeparator()
                enrich = menu.addAction("Enrich: fetch full GitHub profile")
                enrich.triggered.connect(lambda: self._enrich_github(username))

            menu.addSeparator()
            selected = self._selected_findings()
            targets = selected if finding in selected else [finding]
            label = "Delete finding" if len(targets) == 1 else f"Delete {len(targets)} findings"
            delete = menu.addAction(label)
            delete.triggered.connect(lambda t=targets: self._delete_with_confirm(t))
        menu.exec(self._table.viewport().mapToGlobal(pos))

    def _enrich_github(self, username: str) -> None:
        """Run the GitHub collector on a username found by another collector."""
        from ..collectors.github import GitHubCollector

        self._status.setText(f"Enriching: GitHub profile for {username}...")
        self._run_collector(GitHubCollector(), username, SubjectType.USERNAME)

    def _refresh_info(self) -> None:
        if self._case is None:
            self._info.setText("No case open.")
            return
        total = len(self._case.findings)
        included = len(self._case.included_findings())
        self._info.setText(
            f"{self._case.subject}  ·  {total} findings  ·  {included} included"
        )
