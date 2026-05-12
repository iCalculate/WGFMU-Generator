"""Main window for WGFMU Designer."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QAction, QDesktopServices, QIcon, QKeySequence, QUndoCommand, QUndoStack
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QCheckBox,
    QComboBox,
    QDockWidget,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QDoubleSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.app_info import (
    APP_NAME,
    APP_VERSION,
    AUTHOR,
    GITHUB_RELEASES_API,
    GITHUB_TAGS_API,
    GITHUB_URL,
)
from core.cli_log import log
from core.models import Project
from core.models import FORCE_RANGE_OPTIONS
from core.project_io import (
    export_config_csv,
    export_measurements_csv,
    export_waveforms_csv,
    import_config_csv,
    import_measurements_csv,
    load_project,
    save_project,
)
from validators.wgfmu_validator import WGFMUValidator
from widgets.export_dialog import ExportDialog
from widgets.measurement_table import MeasurementTable
from widgets.si_input import SIInput
from widgets.template_panel import TemplatePanel
from widgets.validation_panel import ValidationPanel
from widgets.waveform_editor import WaveformEditor
from widgets.waveform_point_table import WaveformPointTable


class ProjectCommand(QUndoCommand):
    """Undo command that swaps full immutable project snapshots."""

    def __init__(self, window: "MainWindow", before: Project, after: Project, text: str) -> None:
        super().__init__(text)
        self.window = window
        self.before = before.clone()
        self.after = after.clone()

    def undo(self) -> None:
        self.window.set_project(self.before, push_undo=False)

    def redo(self) -> None:
        self.window.set_project(self.after, push_undo=False)


class UpdateCheckWorker(QObject):
    """Check GitHub releases/tags without blocking the UI thread."""

    finished = Signal(bool, str, str)

    def run(self) -> None:
        try:
            latest = self._latest_release_or_tag()
            if not latest:
                self.finished.emit(False, "No release or tag was found on GitHub.", "")
                return
            if _version_tuple(latest) > _version_tuple(APP_VERSION):
                self.finished.emit(
                    True,
                    f"A newer version is available: {latest}\nCurrent version: {APP_VERSION}",
                    GITHUB_URL,
                )
            else:
                self.finished.emit(
                    True,
                    f"You are running the latest known version.\nCurrent version: {APP_VERSION}",
                    GITHUB_URL,
                )
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            self.finished.emit(False, f"Could not check GitHub for updates:\n{exc}", GITHUB_URL)

    def _latest_release_or_tag(self) -> str:
        release = self._get_json(GITHUB_RELEASES_API)
        if isinstance(release, dict):
            tag = str(release.get("tag_name") or release.get("name") or "").strip()
            if tag:
                return tag
        tags = self._get_json(GITHUB_TAGS_API)
        if isinstance(tags, list) and tags:
            return str(tags[0].get("name", "")).strip()
        return ""

    def _get_json(self, url: str):
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": f"{APP_NAME}/{APP_VERSION}",
            },
        )
        with urllib.request.urlopen(request, timeout=8) as response:
            return json.loads(response.read().decode("utf-8"))


def _version_tuple(value: str) -> tuple[int, ...]:
    numbers = re.findall(r"\d+", value)
    return tuple(int(number) for number in numbers) if numbers else (0,)


class MainWindow(QMainWindow):
    """Top-level application shell."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("WGFMU Designer")
        icon = QApplication.instance().windowIcon()
        if not icon.isNull():
            self.setWindowIcon(QIcon(icon))
        self.resize(1400, 900)
        self.project = Project()
        self.current_path: Path | None = None
        self.validator = WGFMUValidator()
        self.undo_stack = QUndoStack(self)
        self._update_thread: QThread | None = None
        self._update_worker: UpdateCheckWorker | None = None

        self.editor = WaveformEditor()
        self.editor.projectChanged.connect(lambda project: self.set_project(project, text="Edit waveform"))
        self.editor.cursorChanged.connect(self._update_cursor)
        self.setCentralWidget(self.editor)

        self.measurement_table = MeasurementTable()
        self.measurement_table.projectChanged.connect(lambda project: self.set_project(project, text="Edit measurements"))
        self.measurement_table.overlayVisibilityChanged.connect(self.editor.set_measurement_overlay_visible)

        self.point_table = WaveformPointTable()
        self.point_table.projectChanged.connect(lambda project: self.set_project(project, text="Edit waveform points"))
        self.point_table.channelChanged.connect(self._set_active_channel)

        self.template_panel = TemplatePanel()
        self.template_panel.projectChanged.connect(lambda project: self.set_project(project, text="Apply template"))
        self.template_panel.channelChanged.connect(self.editor.set_active_channel)

        self.validation_panel = ValidationPanel()
        self.settings_panel = self._build_settings_panel()
        self.editor_panel = self._build_editor_panel()
        self.template_panel.channelChanged.connect(self._set_active_channel)
        self._build_actions()
        self._build_docks()
        self._apply_theme()
        self.set_project(self.project, push_undo=False)

    def set_project(self, project: Project, push_undo: bool = True, text: str = "Change project") -> None:
        """Replace current project, optionally recording undo history."""

        project.enforce_monotonic_waveforms(
            project.settings.minimum_point_spacing if project.settings.minimum_point_spacing > 0 else 1e-12
        )
        project.enforce_force_ranges()
        if push_undo:
            log("INFO", text)
            self.undo_stack.push(ProjectCommand(self, self.project, project, text))
            return
        self.project = project.clone()
        self.editor.set_project(self.project)
        self.measurement_table.set_project(self.project)
        self.point_table.set_project(self.project)
        self.template_panel.set_project(self.project)
        self._sync_settings()
        self._refresh_validation()

    def _build_actions(self) -> None:
        self.new_action = QAction("New Project", self)
        self.open_action = QAction("Open Project", self)
        self.save_action = QAction("Save Project", self)
        self.export_action = QAction("Export WGFMU Text", self)
        self.export_csv_action = QAction("Export CSV", self)
        self.import_config_csv_action = QAction("Import Config CSV", self)
        self.export_config_csv_action = QAction("Export Config CSV", self)
        self.import_meas_action = QAction("Import Measurement CSV", self)
        self.export_meas_action = QAction("Export Measurement CSV", self)
        self.instructions_action = QAction("Operation Guide", self)
        self.software_info_action = QAction("Software Info", self)
        self.check_updates_action = QAction("Check GitHub for Updates", self)
        self.open_github_action = QAction("Open GitHub Repository", self)

        self.new_action.setShortcut(QKeySequence.New)
        self.open_action.setShortcut(QKeySequence.Open)
        self.save_action.setShortcut(QKeySequence.Save)
        self.new_action.triggered.connect(self._new_project)
        self.open_action.triggered.connect(self._open_project)
        self.save_action.triggered.connect(self._save_project)
        self.export_action.triggered.connect(self._export_text)
        self.export_csv_action.triggered.connect(self._export_csv)
        self.import_config_csv_action.triggered.connect(self._import_config_csv)
        self.export_config_csv_action.triggered.connect(self._export_config_csv)
        self.import_meas_action.triggered.connect(self._import_measurement_csv)
        self.export_meas_action.triggered.connect(self._export_measurement_csv)
        self.instructions_action.triggered.connect(self._show_operation_guide)
        self.software_info_action.triggered.connect(self._show_software_info)
        self.check_updates_action.triggered.connect(self._check_for_updates)
        self.open_github_action.triggered.connect(lambda: QDesktopServices.openUrl(QUrl(GITHUB_URL)))

        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")
        for action in [
            self.new_action,
            self.open_action,
            self.save_action,
            self.export_action,
            self.import_config_csv_action,
            self.export_config_csv_action,
            self.export_csv_action,
        ]:
            file_menu.addAction(action)

        edit_menu = menubar.addMenu("Edit")
        self.undo_action = self.undo_stack.createUndoAction(self, "Undo")
        self.redo_action = self.undo_stack.createRedoAction(self, "Redo")
        self.undo_action.setShortcut(QKeySequence.Undo)
        self.redo_action.setShortcut(QKeySequence.Redo)
        edit_menu.addAction(self.undo_action)
        edit_menu.addAction(self.redo_action)

        view_menu = menubar.addMenu("View")
        auto_y_action = QAction("Auto Y Range", self)
        auto_xy_action = QAction("Auto XY Range", self)
        auto_y_action.triggered.connect(self.editor.auto_y_range)
        auto_xy_action.triggered.connect(self.editor.auto_xy_range)
        view_menu.addAction(auto_y_action)
        view_menu.addAction(auto_xy_action)

        measurement_menu = menubar.addMenu("Measurement")
        measurement_menu.addAction(self.import_meas_action)
        measurement_menu.addAction(self.export_meas_action)

        about_menu = menubar.addMenu("About")
        self._populate_about_menu(about_menu)

    def _populate_about_menu(self, menu: QMenu) -> None:
        menu.addAction(self.instructions_action)
        menu.addAction(self.software_info_action)
        menu.addSeparator()
        menu.addAction(self.check_updates_action)
        menu.addAction(self.open_github_action)

    def _build_docks(self) -> None:
        left = QDockWidget("Editor", self)
        left.setMinimumWidth(100)
        editor_tabs = QTabWidget()
        editor_tabs.addTab(self.editor_panel, "Display")
        editor_tabs.addTab(self.template_panel, "Templates")
        editor_tabs.addTab(self.settings_panel, "Settings")
        left.setWidget(editor_tabs)
        self.addDockWidget(Qt.LeftDockWidgetArea, left)

        bottom = QDockWidget("Measurement Events", self)
        bottom.setWidget(self.measurement_table)
        self.addDockWidget(Qt.BottomDockWidgetArea, bottom)

        points = QDockWidget("Waveform Points", self)
        points.setMinimumWidth(100)
        waveform_tabs = QTabWidget()
        waveform_tabs.addTab(self.point_table, "Points")
        waveform_tabs.addTab(self.validation_panel, "Validation")
        points.setWidget(waveform_tabs)
        self.addDockWidget(Qt.RightDockWidgetArea, points)
        self.resizeDocks([left, points], [140, 140], Qt.Horizontal)

    def _build_project_controls(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        for action in [
            self.new_action,
            self.open_action,
            self.save_action,
            self.export_action,
            self.import_config_csv_action,
            self.export_config_csv_action,
            self.export_csv_action,
        ]:
            button = QPushButton(action.text())
            button.clicked.connect(action.trigger)
            layout.addWidget(button)
        layout.addStretch(1)
        return widget

    def _build_editor_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        layout.addWidget(QLabel("Active Channel"))
        channel_row = QHBoxLayout()
        self.ch1_button = QPushButton("CH1")
        self.ch2_button = QPushButton("CH2")
        self.ch1_button.setCheckable(True)
        self.ch2_button.setCheckable(True)
        self.ch1_button.setChecked(True)
        self.ch1_button.clicked.connect(lambda: self._set_active_channel("ch1"))
        self.ch2_button.clicked.connect(lambda: self._set_active_channel("ch2"))
        channel_row.addWidget(self.ch1_button)
        channel_row.addWidget(self.ch2_button)
        layout.addLayout(channel_row)

        layout.addWidget(QLabel("View Range"))
        range_row = QHBoxLayout()
        auto_y_button = QPushButton("Auto Y")
        auto_xy_button = QPushButton("Auto XY")
        auto_y_button.clicked.connect(self.editor.auto_y_range)
        auto_xy_button.clicked.connect(self.editor.auto_xy_range)
        range_row.addWidget(auto_y_button)
        range_row.addWidget(auto_xy_button)
        layout.addLayout(range_row)

        self.marker_mode_box = QComboBox()
        self.marker_mode_box.addItem("Adaptive points", "adaptive")
        self.marker_mode_box.addItem("All points", "all")
        self.marker_mode_box.addItem("Hide points", "hidden")
        self.marker_mode_box.currentIndexChanged.connect(self._marker_mode_changed)
        self.display_mode_box = QComboBox()
        self.display_mode_box.addItem("Overlay channels", "overlay")
        self.display_mode_box.addItem("Stack channels", "stacked")
        self.display_mode_box.currentIndexChanged.connect(self._display_mode_changed)
        self.show_points_check = QCheckBox("Show sample points")
        self.show_points_check.setChecked(True)
        self.show_points_check.stateChanged.connect(self._show_points_changed)
        form = QFormLayout()
        form.addRow("", self.show_points_check)
        form.addRow("Sample Points", self.marker_mode_box)
        form.addRow("Display", self.display_mode_box)
        layout.addLayout(form)

        layout.addStretch(1)
        return widget

    def _set_active_channel(self, channel: str) -> None:
        """Select which channel receives new graph points."""

        self.editor.set_active_channel(channel)
        self.point_table.set_channel(channel)
        self.ch1_button.setChecked(channel == "ch1")
        self.ch2_button.setChecked(channel == "ch2")
        self.statusBar().showMessage(f"Editing {channel.upper()}", 2500)
        log("INFO", "Active channel changed", detail=channel.upper())

    def _marker_mode_changed(self) -> None:
        mode = self.marker_mode_box.currentData()
        next_project = self.project.clone()
        next_project.settings.sample_marker_mode = mode
        self.editor.set_sample_marker_mode(mode)
        log("INFO", "Sample point display changed", detail=str(mode))
        self.set_project(next_project, text="Change sample point display")

    def _display_mode_changed(self) -> None:
        mode = self.display_mode_box.currentData()
        next_project = self.project.clone()
        next_project.settings.waveform_display_mode = mode
        self.editor.set_display_mode(mode)
        log("INFO", "Waveform display changed", detail=str(mode))
        self.set_project(next_project, text="Change waveform display")

    def _show_points_changed(self) -> None:
        next_project = self.project.clone()
        next_project.settings.show_sample_points = self.show_points_check.isChecked()
        log("INFO", "Sample points toggled", detail=f"visible={next_project.settings.show_sample_points}")
        self.set_project(next_project, text="Toggle sample points")

    def _build_settings_panel(self) -> QWidget:
        widget = QWidget()
        self.repeat_spin = QSpinBox()
        self.repeat_spin.setRange(1, 1_000_000)
        self._style_numeric_control(self.repeat_spin)
        self.viz_check = QCheckBox("Waveform timing visualization")
        self.snap_check = QCheckBox("Snap to grid")
        self.smart_snap_check = QCheckBox("Smart nice-number snap")
        self.snap_time = self._double(0.0, 1e15, 1.0, 1.0, 6)
        self.snap_voltage = self._double(0.0, 1e9, 10.0, 1.0, 6)
        self.minimum_spacing = SIInput(100e-9, 1e-15, 1e9, "s")
        self._style_numeric_control(self.minimum_spacing)
        self.range_ch1 = QComboBox()
        self.range_ch2 = QComboBox()
        self._style_numeric_control(self.range_ch1)
        self._style_numeric_control(self.range_ch2)
        for key, (label, _low, _high) in FORCE_RANGE_OPTIONS.items():
            self.range_ch1.addItem(label, key)
            self.range_ch2.addItem(label, key)
        self.guard = self._double(0.0, 1e15, 1.0, 1.0, 6)
        self.snap_time.setSuffix(" us")
        self.snap_voltage.setSuffix(" mV")
        self.guard.setSuffix(" us")

        form = QFormLayout(widget)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setFormAlignment(Qt.AlignTop)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(9)
        form.addRow("RepeatCount", self.repeat_spin)
        form.addRow("", self.viz_check)
        form.addRow("", self.snap_check)
        form.addRow("", self.smart_snap_check)
        form.addRow("Snap Time [us]", self.snap_time)
        form.addRow("Snap Voltage [mV]", self.snap_voltage)
        form.addRow("Min Point Spacing [s]", self.minimum_spacing)
        form.addRow("Ch1 Force Range", self.range_ch1)
        form.addRow("Ch2 Force Range", self.range_ch2)
        form.addRow("Switch Guard [us]", self.guard)
        for control in [
            self.repeat_spin,
            self.viz_check,
            self.snap_check,
            self.smart_snap_check,
            self.snap_time,
            self.snap_voltage,
            self.minimum_spacing,
            self.range_ch1,
            self.range_ch2,
            self.guard,
        ]:
            if hasattr(control, "currentIndexChanged"):
                control.currentIndexChanged.connect(self._settings_changed)
            elif hasattr(control, "valueChanged"):
                control.valueChanged.connect(self._settings_changed)
            else:
                control.stateChanged.connect(self._settings_changed)
        return widget

    def _double(self, minimum: float, maximum: float, value: float, step: float, decimals: int) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setValue(value)
        spin.setSingleStep(step)
        spin.setDecimals(decimals)
        self._style_numeric_control(spin)
        return spin

    def _style_numeric_control(self, control: QWidget) -> None:
        control.setMinimumHeight(30)
        control.setProperty("settingsControl", True)
        if isinstance(control, QAbstractSpinBox):
            control.setButtonSymbols(QAbstractSpinBox.NoButtons)
            control.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

    def _settings_changed(self) -> None:
        next_project = self.project.clone()
        next_project.settings.repeat_count = self.repeat_spin.value()
        next_project.settings.waveform_timing_visualization = self.viz_check.isChecked()
        next_project.settings.snap_enabled = self.snap_check.isChecked()
        next_project.settings.smart_snap_enabled = self.smart_snap_check.isChecked()
        next_project.settings.snap_time = self.snap_time.value() * 1e-6
        next_project.settings.snap_voltage = self.snap_voltage.value() * 1e-3
        next_project.settings.minimum_point_spacing = self.minimum_spacing.value()
        next_project.settings.force_range_mode_ch1 = self.range_ch1.currentData()
        next_project.settings.force_range_mode_ch2 = self.range_ch2.currentData()
        next_project.settings.range_switch_guard_s = self.guard.value() * 1e-6
        log("INFO", "Settings changed")
        self.set_project(next_project, text="Edit settings")

    def _sync_settings(self) -> None:
        for control in [
            self.repeat_spin,
            self.viz_check,
            self.snap_check,
            self.smart_snap_check,
            self.marker_mode_box,
            self.display_mode_box,
            self.show_points_check,
            self.snap_time,
            self.snap_voltage,
            self.minimum_spacing,
            self.range_ch1,
            self.range_ch2,
            self.guard,
        ]:
            control.blockSignals(True)
        settings = self.project.settings
        self.repeat_spin.setValue(settings.repeat_count)
        self.viz_check.setChecked(settings.waveform_timing_visualization)
        self.snap_check.setChecked(settings.snap_enabled)
        self.smart_snap_check.setChecked(settings.smart_snap_enabled)
        self.show_points_check.setChecked(settings.show_sample_points)
        marker_index = self.marker_mode_box.findData(settings.sample_marker_mode)
        if marker_index >= 0:
            self.marker_mode_box.setCurrentIndex(marker_index)
        display_index = self.display_mode_box.findData(settings.waveform_display_mode)
        if display_index >= 0:
            self.display_mode_box.setCurrentIndex(display_index)
        self.snap_time.setValue(settings.snap_time * 1e6)
        self.snap_voltage.setValue(settings.snap_voltage * 1e3)
        self.minimum_spacing.setValue(settings.minimum_point_spacing)
        ch1_index = self.range_ch1.findData(settings.force_range_mode_ch1)
        ch2_index = self.range_ch2.findData(settings.force_range_mode_ch2)
        self.range_ch1.setCurrentIndex(max(0, ch1_index))
        self.range_ch2.setCurrentIndex(max(0, ch2_index))
        self.guard.setValue(settings.range_switch_guard_s * 1e6)
        for control in [
            self.repeat_spin,
            self.viz_check,
            self.snap_check,
            self.smart_snap_check,
            self.marker_mode_box,
            self.display_mode_box,
            self.show_points_check,
            self.snap_time,
            self.snap_voltage,
            self.minimum_spacing,
            self.range_ch1,
            self.range_ch2,
            self.guard,
        ]:
            control.blockSignals(False)

    def _refresh_validation(self) -> None:
        messages = self.validator.validate(self.project)
        self.validation_panel.set_results(
            messages,
            self.project.total_measurement_points(),
            self.project.active_point_limit(),
        )

    def _new_project(self) -> None:
        self.current_path = None
        self.undo_stack.clear()
        self.set_project(Project(), push_undo=False)
        self.statusBar().showMessage("New project", 3000)
        log("OK", "New project created")

    def _open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open Project", "", "WGFMU Project (*.json)")
        if not path:
            return
        try:
            self.current_path = Path(path)
            self.undo_stack.clear()
            self.set_project(load_project(path), push_undo=False)
            self.statusBar().showMessage(f"Opened {path}", 5000)
            log("OK", "Project opened", detail=path)
        except Exception as exc:  # pragma: no cover - GUI error path
            log("ERROR", "Open project failed", detail=str(exc))
            QMessageBox.critical(self, "Open Failed", str(exc))

    def _save_project(self) -> None:
        if self.current_path is None:
            path, _ = QFileDialog.getSaveFileName(self, "Save Project", "wgfmu_project.json", "WGFMU Project (*.json)")
            if not path:
                return
            self.current_path = Path(path)
        save_project(self.current_path, self.project)
        self.statusBar().showMessage(f"Saved {self.current_path}", 5000)
        log("OK", "Project saved", detail=str(self.current_path))

    def _export_text(self) -> None:
        ExportDialog(self.project, self).exec()

    def _export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export Waveform CSV", "waveforms.csv", "CSV Files (*.csv)")
        if path:
            export_waveforms_csv(path, self.project)
            self.statusBar().showMessage(f"Exported {path}", 5000)
            log("OK", "Waveform CSV exported", detail=path)

    def _import_config_csv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import Config CSV", "", "CSV Files (*.csv)")
        if path:
            try:
                project = import_config_csv(path, self.project)
                self.set_project(project, text="Import config CSV")
                log("OK", "Config CSV imported", detail=path)
            except Exception as exc:  # pragma: no cover - GUI error path
                log("ERROR", "Config CSV import failed", detail=str(exc))
                QMessageBox.critical(self, "Import Failed", str(exc))

    def _export_config_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export Config CSV", "wgfmu_config.csv", "CSV Files (*.csv)")
        if path:
            export_config_csv(path, self.project)
            self.statusBar().showMessage(f"Exported {path}", 5000)
            log("OK", "Config CSV exported", detail=path)

    def _import_measurement_csv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import Measurement CSV", "", "CSV Files (*.csv)")
        if path:
            project = import_measurements_csv(path, self.project)
            self.set_project(project, text="Import measurement CSV")
            log("OK", "Measurement CSV imported", detail=path)

    def _export_measurement_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export Measurement CSV", "measurements.csv", "CSV Files (*.csv)")
        if path:
            export_measurements_csv(path, self.project)
            log("OK", "Measurement CSV exported", detail=path)

    def _show_operation_guide(self) -> None:
        QMessageBox.information(
            self,
            "Operation Guide",
            "\n".join(
                [
                    "Waveform editing:",
                    "- Ctrl + left click: add a point to the active channel.",
                    "- Alt + left click: delete a nearby point or flip a sharp edge.",
                    "- Shift + drag: move a point or selected segment.",
                    "- Right click: open waveform editing commands.",
                    "",
                    "Measurement ranges:",
                    "- Right drag on the plot: create a measurement time range.",
                    "- Alt + right drag: remove part of an existing measurement range.",
                    "- Measurement ranges are shown as highlighted background bands and stay synchronized with the table.",
                    "",
                    "Export:",
                    "- Use Export WGFMU Text for Pattern Editor paste text.",
                    "- Use CSV actions for waveform, measurement, or combined config data.",
                ]
            ),
        )

    def _show_software_info(self) -> None:
        QMessageBox.information(
            self,
            "Software Info",
            f"{APP_NAME}\nVersion: {APP_VERSION}\nAuthor: {AUTHOR}\nGitHub: {GITHUB_URL}",
        )

    def _check_for_updates(self) -> None:
        if self._update_thread is not None:
            self.statusBar().showMessage("Update check is already running...", 3000)
            return
        self.check_updates_action.setEnabled(False)
        self.statusBar().showMessage("Checking GitHub for updates...", 3000)
        self._update_thread = QThread(self)
        self._update_worker = UpdateCheckWorker()
        self._update_worker.moveToThread(self._update_thread)
        self._update_thread.started.connect(self._update_worker.run)
        self._update_worker.finished.connect(self._update_check_finished)
        self._update_worker.finished.connect(self._update_thread.quit)
        self._update_worker.finished.connect(self._update_worker.deleteLater)
        self._update_thread.finished.connect(self._update_thread.deleteLater)
        self._update_thread.finished.connect(self._clear_update_worker)
        self._update_thread.start()

    def _update_check_finished(self, ok: bool, message: str, url: str) -> None:
        title = "Update Check" if ok else "Update Check Failed"
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setText(message)
        box.setIcon(QMessageBox.Information if ok else QMessageBox.Warning)
        open_button = None
        if url:
            open_button = box.addButton("Open GitHub", QMessageBox.ActionRole)
        box.addButton(QMessageBox.Ok)
        box.exec()
        if open_button is not None and box.clickedButton() == open_button:
            QDesktopServices.openUrl(QUrl(url))
        log("OK" if ok else "WARN", "GitHub update check finished", detail=message.replace("\n", " "))

    def _clear_update_worker(self) -> None:
        self.check_updates_action.setEnabled(True)
        self._update_thread = None
        self._update_worker = None

    def _update_cursor(self, time_value: float, voltage: float) -> None:
        self.statusBar().showMessage(f"Cursor: t={time_value:.6g} s, V={voltage:.6g} V")

    def _apply_theme(self) -> None:
        QApplication.instance().setStyleSheet(
            """
            QMainWindow, QWidget {
                background: #171b22;
                color: #d8dee9;
                font-size: 12px;
            }
            QDockWidget::title {
                background: #222833;
                padding: 5px 8px;
                border-bottom: 1px solid #303846;
            }
            QMenuBar, QMenu, QStatusBar {
                background: #1f2530;
                color: #d8dee9;
            }
            QMenuBar::item {
                padding: 4px 8px;
            }
            QMenu::item {
                padding: 5px 22px 5px 18px;
            }
            QMenu::item:selected {
                background: #2f4056;
            }
            QCheckBox::indicator {
                width: 14px; height: 14px; border: 1px solid #64748b; background: #0f1720;
                border-radius: 3px;
            }
            QCheckBox::indicator:checked {
                background: #4ea1ff; border-color: #9dccff;
            }
            QRadioButton {
                spacing: 4px;
                padding: 2px 3px;
            }
            QRadioButton::indicator {
                width: 11px;
                height: 11px;
                border-radius: 6px;
                border: 1px solid #64748b;
                background: #0f1720;
            }
            QRadioButton::indicator:checked {
                border: 3px solid #4ea1ff;
                background: #cfe6ff;
            }
            QPushButton {
                background: #293241;
                border: 1px solid #3a4658;
                padding: 4px 10px;
                border-radius: 5px;
                min-height: 22px;
            }
            QPushButton:hover { background: #344052; border-color: #50627a; }
            QPushButton:pressed { background: #223047; }
            QPushButton:checked { background: #355f92; border-color: #4ea1ff; }
            QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTableWidget, QListWidget {
                background: #11151c;
                color: #d8dee9;
                border: 1px solid #303846;
                selection-background-color: #355f92;
                selection-color: #ffffff;
            }
            QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
                min-height: 22px;
                border-radius: 5px;
                padding: 3px 8px;
            }
            QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
                border-color: #5aa9ff;
                background: #151d28;
            }
            QComboBox::drop-down {
                width: 24px;
                border: none;
                subcontrol-origin: padding;
                subcontrol-position: top right;
            }
            QComboBox::down-arrow {
                width: 0px;
                height: 0px;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid #9fb2c3;
                margin-right: 8px;
            }
            QComboBox QAbstractItemView {
                background: #11151c;
                color: #d8dee9;
                border: 1px solid #3a4658;
                selection-background-color: #355f92;
            }
            QLineEdit[settingsControl="true"], QSpinBox[settingsControl="true"],
            QDoubleSpinBox[settingsControl="true"], QComboBox[settingsControl="true"] {
                background: #121821;
                border: 1px solid #3a4658;
                border-radius: 6px;
                padding: 4px 10px;
                min-height: 22px;
            }
            QLineEdit[settingsControl="true"]:focus, QSpinBox[settingsControl="true"]:focus,
            QDoubleSpinBox[settingsControl="true"]:focus, QComboBox[settingsControl="true"]:focus {
                border: 1px solid #5aa9ff;
                background: #151d28;
            }
            QSpinBox[settingsControl="true"]::up-button, QSpinBox[settingsControl="true"]::down-button,
            QDoubleSpinBox[settingsControl="true"]::up-button, QDoubleSpinBox[settingsControl="true"]::down-button {
                width: 0px;
                border: none;
            }
            QComboBox[settingsControl="true"]::drop-down {
                width: 24px;
                border: none;
            }
            QComboBox[settingsControl="true"]::down-arrow {
                width: 0px;
                height: 0px;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid #9fb2c3;
                margin-right: 8px;
            }
            QTableWidget, QListWidget {
                gridline-color: #27313f;
                alternate-background-color: #141a23;
                border-radius: 5px;
            }
            QTableWidget::item, QListWidget::item {
                padding: 3px 5px;
            }
            QTableWidget::item:selected, QListWidget::item:selected {
                background: #355f92;
                color: #ffffff;
            }
            QHeaderView::section {
                background: #242b36;
                color: #d8dee9;
                padding: 4px 6px;
                border: 1px solid #303846;
            }
            QTabBar::tab {
                background: #222833;
                padding: 5px 9px;
                border: 1px solid #303846;
                border-bottom-color: #242b36;
            }
            QTabBar::tab:selected {
                background: #303846;
                border-color: #435168;
            }
            QTabBar::tab:hover {
                background: #2a3342;
            }
            """
        )
