"""Measurement event editor table."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.cli_log import log
from core.models import MeasurementEvent, Project
from core.si_units import format_si, parse_si
from exporters import wgfmu_exporter


class MeasurementTable(QWidget):
    """Editable table for WGFMU measurement event rows."""

    projectChanged = Signal(object)
    overlayVisibilityChanged = Signal(bool)

    HEADERS = ["tm [s]", "Points", "Interval [s]", "Average [s]", "Ch1 Range", "Ch2 Range"]
    SAMPLING_INTERVALS = [
        ("10n", 10e-9),
        ("100n", 100e-9),
        ("1u", 1e-6),
        ("10u", 10e-6),
        ("100u", 100e-6),
        ("1m", 1e-3),
        ("10m", 10e-3),
        ("100m", 100e-3),
        ("1s", 1.0),
    ]

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.project = Project()
        self._updating = False

        self.table = QTableWidget(0, len(self.HEADERS), self)
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setDefaultSectionSize(24)
        self.table.itemChanged.connect(self._item_changed)

        self.add_button = QPushButton("Add Row")
        self.remove_button = QPushButton("Remove Selected")
        self.copy_button = QPushButton("Copy WGFMU Text")
        self.show_overlay_check = QCheckBox("Show measure points in plot")
        self.show_overlay_check.setChecked(True)
        self.sampling_group = QButtonGroup(self)
        self.sampling_buttons: list[QRadioButton] = []
        for label, interval in self.SAMPLING_INTERVALS:
            radio = QRadioButton(label)
            radio.setProperty("interval", interval)
            self.sampling_group.addButton(radio)
            self.sampling_buttons.append(radio)
        self.sampling_buttons[2].setChecked(True)
        self.add_button.clicked.connect(self._add_row)
        self.remove_button.clicked.connect(self._remove_selected)
        self.copy_button.clicked.connect(self._copy_measurements)
        self.show_overlay_check.stateChanged.connect(
            lambda _state: self.overlayVisibilityChanged.emit(self.show_overlay_check.isChecked())
        )
        self.sampling_group.buttonClicked.connect(self._sampling_interval_changed)

        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        buttons.addWidget(self.add_button)
        buttons.addWidget(self.remove_button)
        buttons.addWidget(self.copy_button)
        buttons.addWidget(self.show_overlay_check)
        buttons.addWidget(QLabel("Sampling"))
        for radio in self.sampling_buttons:
            buttons.addWidget(radio)
        buttons.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        layout.addLayout(buttons)
        layout.addWidget(self.table)

    def set_project(self, project: Project) -> None:
        """Load project rows into the table."""

        self.project = project
        self._updating = True
        self._sync_sampling_buttons(project.settings.measurement_sampling_interval)
        self.table.setRowCount(len(project.measurements))
        for row, event in enumerate(project.measurements):
            values = [
                format_si(event.tm, unit=""),
                str(event.points),
                format_si(event.interval, unit=""),
                format_si(event.averaging, unit=""),
                f"{event.ch1_range:.12g}",
                f"{event.ch2_range:.12g}",
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(row, col, item)
        self._updating = False

    def _sync_sampling_buttons(self, interval: float) -> None:
        best = min(self.sampling_buttons, key=lambda button: abs(float(button.property("interval")) - interval))
        for button in self.sampling_buttons:
            button.blockSignals(True)
            button.setChecked(button is best)
            button.blockSignals(False)

    def _read_table(self) -> list[MeasurementEvent]:
        rows: list[MeasurementEvent] = []
        for row in range(self.table.rowCount()):
            def text(col: int, default: str = "0") -> str:
                item = self.table.item(row, col)
                return item.text().strip() if item and item.text().strip() else default

            try:
                interval = parse_si(text(2, "1u"))
                averaging = min(parse_si(text(3, text(2, "1u"))), interval)
                rows.append(
                    MeasurementEvent(
                        tm=parse_si(text(0)),
                        points=int(float(text(1, "1"))),
                        interval=interval,
                        averaging=averaging,
                        ch1_range=parse_si(text(4)),
                        ch2_range=parse_si(text(5)),
                    )
                )
            except ValueError:
                rows.append(MeasurementEvent())
        return rows

    def _emit_change(self) -> None:
        next_project = self.project.clone()
        next_project.measurements = self._read_table()
        log("INFO", "Measurement table edited", detail=f"rows={len(next_project.measurements)}")
        self.projectChanged.emit(next_project)
        self.set_project(next_project)

    def _item_changed(self, _item: QTableWidgetItem) -> None:
        if not self._updating:
            self._emit_change()

    def _add_row(self) -> None:
        next_project = self.project.clone()
        interval = self._selected_sampling_interval()
        next_project.settings.measurement_sampling_interval = interval
        duration = max(next_project.duration(), interval)
        next_project.measurements.append(
            MeasurementEvent(
                tm=0.0,
                points=max(1, int(duration / interval) + 1),
                interval=interval,
                averaging=interval,
                ch1_range=0.0,
                ch2_range=0.0,
            )
        )
        log("OK", "Measurement row added", detail=f"rows={len(next_project.measurements)}")
        self.projectChanged.emit(next_project)

    def _selected_sampling_interval(self) -> float:
        checked = self.sampling_group.checkedButton()
        if checked is None:
            return self.project.settings.measurement_sampling_interval
        return float(checked.property("interval"))

    def _sampling_interval_changed(self) -> None:
        if self._updating:
            return
        interval = self._selected_sampling_interval()
        next_project = self.project.clone()
        next_project.settings.measurement_sampling_interval = interval
        next_project.measurements = self._read_table()
        log("OK", "Default measurement sampling interval changed", detail=f"interval={interval:g}s")
        self.projectChanged.emit(next_project)

    def _remove_selected(self) -> None:
        selected = sorted({item.row() for item in self.table.selectedItems()}, reverse=True)
        if not selected:
            selected = [self.table.currentRow()] if self.table.currentRow() >= 0 else []
        next_project = self.project.clone()
        for row in selected:
            if 0 <= row < len(next_project.measurements):
                next_project.measurements.pop(row)
        log("OK", "Measurement row removed", detail=f"removed={len(selected)} rows={len(next_project.measurements)}")
        self.projectChanged.emit(next_project)

    def _copy_measurements(self) -> None:
        QApplication.clipboard().setText(wgfmu_exporter.measurement_text(self.project))
        log("OK", "Measurement WGFMU text copied", detail=f"rows={len(self.project.measurements)}")
