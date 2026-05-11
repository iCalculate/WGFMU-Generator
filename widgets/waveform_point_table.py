"""Editable waveform point table."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.models import CHANNELS, Project, WaveformPoint
from core.si_units import format_si, parse_si
from exporters import wgfmu_exporter


class WaveformPointTable(QWidget):
    """Manual coordinate editor for one waveform channel."""

    projectChanged = Signal(object)
    channelChanged = Signal(str)

    HEADERS = ["Time [s]", "Voltage [V]"]

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.project = Project()
        self.channel = "ch1"
        self._updating = False

        self.channel_box = QComboBox()
        self.channel_box.addItems(["CH1", "CH2"])
        self.channel_box.currentIndexChanged.connect(self._channel_changed)

        self.add_button = QPushButton("Add Point")
        self.delete_button = QPushButton("Delete Selected")
        self.copy_button = QPushButton("Copy WGFMU Text")
        self.add_button.clicked.connect(self._add_point)
        self.delete_button.clicked.connect(self._delete_selected)
        self.copy_button.clicked.connect(self._copy_waveform)

        top = QHBoxLayout()
        top.addWidget(self.channel_box)
        top.addWidget(self.add_button)
        top.addWidget(self.delete_button)
        top.addWidget(self.copy_button)

        self.table = QTableWidget(0, len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.itemChanged.connect(self._item_changed)
        self.table.verticalHeader().setVisible(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addLayout(top)
        layout.addWidget(self.table)

    def set_project(self, project: Project) -> None:
        self.project = project
        self._refresh()

    def set_channel(self, channel: str) -> None:
        if channel not in CHANNELS:
            return
        self.channel = channel
        self.channel_box.blockSignals(True)
        self.channel_box.setCurrentIndex(CHANNELS.index(channel))
        self.channel_box.blockSignals(False)
        self._refresh()

    def _channel_changed(self) -> None:
        self.channel = CHANNELS[self.channel_box.currentIndex()]
        self.channelChanged.emit(self.channel)
        self._refresh()

    def _refresh(self) -> None:
        self._updating = True
        points = self.project.waveforms[self.channel]
        self.table.setRowCount(len(points))
        for row, point in enumerate(points):
            self.table.setVerticalHeaderItem(row, QTableWidgetItem(str(row)))
            self.table.setItem(row, 0, QTableWidgetItem(format_si(point.time, unit="")))
            self.table.setItem(row, 1, QTableWidgetItem(f"{point.voltage:.12g}"))
        self.table.resizeColumnsToContents()
        self._updating = False

    def _item_changed(self, item: QTableWidgetItem) -> None:
        if self._updating:
            return
        row = item.row()
        points = self.project.waveforms[self.channel]
        if row < 0 or row >= len(points):
            return
        try:
            time_value = parse_si(self.table.item(row, 0).text())
            voltage = parse_si(self.table.item(row, 1).text())
        except (AttributeError, ValueError):
            self._refresh()
            return
        next_project = self.project.clone()
        next_project.waveforms[self.channel][row] = WaveformPoint(max(0.0, time_value), voltage)
        next_project.enforce_monotonic_waveforms(next_project.settings.minimum_point_spacing)
        self.projectChanged.emit(next_project)

    def _add_point(self) -> None:
        next_project = self.project.clone()
        points = next_project.waveforms[self.channel]
        time_value = points[-1].time + next_project.settings.minimum_point_spacing if points else 0.0
        voltage = points[-1].voltage if points else 0.0
        points.append(WaveformPoint(time_value, voltage))
        next_project.enforce_monotonic_waveforms(next_project.settings.minimum_point_spacing)
        self.projectChanged.emit(next_project)

    def _delete_selected(self) -> None:
        rows = sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True)
        if not rows:
            return
        next_project = self.project.clone()
        points = next_project.waveforms[self.channel]
        for row in rows:
            if 0 <= row < len(points):
                points.pop(row)
        self.projectChanged.emit(next_project)

    def _copy_waveform(self) -> None:
        QApplication.clipboard().setText(wgfmu_exporter.waveform_text(self.project, self.channel))
