"""Main window for WGFMU Designer."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence, QUndoCommand, QUndoStack
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDockWidget,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QDoubleSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.models import Project
from core.project_io import (
    export_measurements_csv,
    export_waveforms_csv,
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


class MainWindow(QMainWindow):
    """Top-level application shell."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("WGFMU Designer")
        self.resize(1400, 900)
        self.project = Project()
        self.current_path: Path | None = None
        self.validator = WGFMUValidator()
        self.undo_stack = QUndoStack(self)

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
        if push_undo:
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
        self.import_meas_action = QAction("Import Measurement CSV", self)
        self.export_meas_action = QAction("Export Measurement CSV", self)

        self.new_action.setShortcut(QKeySequence.New)
        self.open_action.setShortcut(QKeySequence.Open)
        self.save_action.setShortcut(QKeySequence.Save)
        self.new_action.triggered.connect(self._new_project)
        self.open_action.triggered.connect(self._open_project)
        self.save_action.triggered.connect(self._save_project)
        self.export_action.triggered.connect(self._export_text)
        self.export_csv_action.triggered.connect(self._export_csv)
        self.import_meas_action.triggered.connect(self._import_measurement_csv)
        self.export_meas_action.triggered.connect(self._export_measurement_csv)

        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")
        for action in [
            self.new_action,
            self.open_action,
            self.save_action,
            self.export_action,
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

    def _build_docks(self) -> None:
        left = QDockWidget("Project", self)
        tabs = QTabWidget()
        tabs.addTab(self._build_project_controls(), "Project")
        tabs.addTab(self.editor_panel, "Editor")
        tabs.addTab(self.template_panel, "Templates")
        tabs.addTab(self.settings_panel, "Settings")
        tabs.addTab(self.validation_panel, "Validation")
        left.setWidget(tabs)
        self.addDockWidget(Qt.LeftDockWidgetArea, left)

        bottom = QDockWidget("Measurement Events", self)
        bottom.setWidget(self.measurement_table)
        self.addDockWidget(Qt.BottomDockWidgetArea, bottom)

        points = QDockWidget("Waveform Points", self)
        points.setWidget(self.point_table)
        self.addDockWidget(Qt.RightDockWidgetArea, points)

    def _build_project_controls(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        for action in [
            self.new_action,
            self.open_action,
            self.save_action,
            self.export_action,
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

    def _marker_mode_changed(self) -> None:
        mode = self.marker_mode_box.currentData()
        next_project = self.project.clone()
        next_project.settings.sample_marker_mode = mode
        self.editor.set_sample_marker_mode(mode)
        self.set_project(next_project, text="Change sample point display")

    def _display_mode_changed(self) -> None:
        mode = self.display_mode_box.currentData()
        next_project = self.project.clone()
        next_project.settings.waveform_display_mode = mode
        self.editor.set_display_mode(mode)
        self.set_project(next_project, text="Change waveform display")

    def _show_points_changed(self) -> None:
        next_project = self.project.clone()
        next_project.settings.show_sample_points = self.show_points_check.isChecked()
        self.set_project(next_project, text="Toggle sample points")

    def _build_settings_panel(self) -> QWidget:
        widget = QWidget()
        self.repeat_spin = QSpinBox()
        self.repeat_spin.setRange(1, 1_000_000)
        self.viz_check = QCheckBox("Waveform timing visualization")
        self.snap_check = QCheckBox("Snap to grid")
        self.smart_snap_check = QCheckBox("Smart nice-number snap")
        self.snap_time = self._double(0.0, 1e15, 1.0, 1.0, 6)
        self.snap_voltage = self._double(0.0, 1e9, 10.0, 1.0, 6)
        self.minimum_spacing = SIInput(100e-9, 1e-15, 1e9, "s")
        self.range_ch1 = self._double(0.0, 1000.0, 10.0, 1.0, 6)
        self.range_ch2 = self._double(0.0, 1000.0, 10.0, 1.0, 6)
        self.guard = self._double(0.0, 1e15, 1.0, 1.0, 6)
        self.snap_time.setSuffix(" us")
        self.snap_voltage.setSuffix(" mV")
        self.guard.setSuffix(" us")

        form = QFormLayout(widget)
        form.addRow("RepeatCount", self.repeat_spin)
        form.addRow("", self.viz_check)
        form.addRow("", self.snap_check)
        form.addRow("", self.smart_snap_check)
        form.addRow("Snap Time [us]", self.snap_time)
        form.addRow("Snap Voltage [mV]", self.snap_voltage)
        form.addRow("Min Point Spacing [s]", self.minimum_spacing)
        form.addRow("Ch1 VForceRange [V]", self.range_ch1)
        form.addRow("Ch2 VForceRange [V]", self.range_ch2)
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
            if hasattr(control, "valueChanged"):
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
        return spin

    def _settings_changed(self) -> None:
        next_project = self.project.clone()
        next_project.settings.repeat_count = self.repeat_spin.value()
        next_project.settings.waveform_timing_visualization = self.viz_check.isChecked()
        next_project.settings.snap_enabled = self.snap_check.isChecked()
        next_project.settings.smart_snap_enabled = self.smart_snap_check.isChecked()
        next_project.settings.snap_time = self.snap_time.value() * 1e-6
        next_project.settings.snap_voltage = self.snap_voltage.value() * 1e-3
        next_project.settings.minimum_point_spacing = self.minimum_spacing.value()
        next_project.settings.vforce_range_ch1 = self.range_ch1.value()
        next_project.settings.vforce_range_ch2 = self.range_ch2.value()
        next_project.settings.range_switch_guard_s = self.guard.value() * 1e-6
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
        self.range_ch1.setValue(settings.vforce_range_ch1)
        self.range_ch2.setValue(settings.vforce_range_ch2)
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

    def _open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open Project", "", "WGFMU Project (*.json)")
        if not path:
            return
        try:
            self.current_path = Path(path)
            self.undo_stack.clear()
            self.set_project(load_project(path), push_undo=False)
            self.statusBar().showMessage(f"Opened {path}", 5000)
        except Exception as exc:  # pragma: no cover - GUI error path
            QMessageBox.critical(self, "Open Failed", str(exc))

    def _save_project(self) -> None:
        if self.current_path is None:
            path, _ = QFileDialog.getSaveFileName(self, "Save Project", "wgfmu_project.json", "WGFMU Project (*.json)")
            if not path:
                return
            self.current_path = Path(path)
        save_project(self.current_path, self.project)
        self.statusBar().showMessage(f"Saved {self.current_path}", 5000)

    def _export_text(self) -> None:
        ExportDialog(self.project, self).exec()

    def _export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export Waveform CSV", "waveforms.csv", "CSV Files (*.csv)")
        if path:
            export_waveforms_csv(path, self.project)
            self.statusBar().showMessage(f"Exported {path}", 5000)

    def _import_measurement_csv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import Measurement CSV", "", "CSV Files (*.csv)")
        if path:
            project = import_measurements_csv(path, self.project)
            self.set_project(project, text="Import measurement CSV")

    def _export_measurement_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export Measurement CSV", "measurements.csv", "CSV Files (*.csv)")
        if path:
            export_measurements_csv(path, self.project)

    def _update_cursor(self, time_value: float, voltage: float) -> None:
        self.statusBar().showMessage(f"Cursor: t={time_value:.6g} s, V={voltage:.6g} V")

    def _apply_theme(self) -> None:
        QApplication.instance().setStyleSheet(
            """
            QMainWindow, QWidget { background: #171b22; color: #d8dee9; }
            QDockWidget::title { background: #222833; padding: 5px; }
            QMenuBar, QMenu, QStatusBar { background: #1f2530; color: #d8dee9; }
            QPushButton { background: #2a3240; border: 1px solid #3b4658; padding: 6px; border-radius: 4px; }
            QPushButton:hover { background: #344052; }
            QPushButton:checked { background: #355f92; border-color: #4ea1ff; }
            QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTableWidget, QListWidget {
                background: #11151c; color: #d8dee9; border: 1px solid #303846; selection-background-color: #355f92;
            }
            QHeaderView::section { background: #242b36; color: #d8dee9; padding: 4px; border: 1px solid #303846; }
            QTabBar::tab { background: #222833; padding: 6px 10px; border: 1px solid #303846; }
            QTabBar::tab:selected { background: #303846; }
            """
        )
