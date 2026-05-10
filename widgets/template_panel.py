"""Waveform template controls."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.models import CHANNELS, Project
from templates import generators
from widgets.si_input import SIInput


class TemplatePanel(QWidget):
    """Applies generated waveforms to the selected channel."""

    projectChanged = Signal(object)
    channelChanged = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.project = Project()
        self.channel = "ch1"

        self.channel_box = QComboBox()
        self.channel_box.addItems(["CH1", "CH2"])
        self.channel_box.currentIndexChanged.connect(self._channel_changed)

        self.template_box = QComboBox()
        self.template_box.addItems(
            ["Pulse", "Double Pulse", "Triangle", "Ramp", "Sine", "Pulse Train", "Read/Write Pulse", "Custom"]
        )

        self.amplitude = SIInput(1.0, -200.0, 200.0, "V")
        self.width = SIInput(1e-3, 0.0, 1000.0, "s")
        self.frequency = SIInput(1000.0, 1e-9, 1e12, "Hz")
        self.duty = SIInput(50.0, 0.0, 100.0, "%")
        self.cycles = QSpinBox()
        self.cycles.setRange(1, 100000)
        self.cycles.setValue(5)
        self.apply_button = QPushButton("Apply Template")
        self.apply_button.clicked.connect(self._apply)

        form = QFormLayout()
        form.addRow("Channel", self.channel_box)
        form.addRow("Template", self.template_box)
        form.addRow("Amplitude [V]", self.amplitude)
        form.addRow("Width/Duration [s]", self.width)
        form.addRow("Frequency [Hz]", self.frequency)
        form.addRow("Duty [%]", self.duty)
        form.addRow("Cycles", self.cycles)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(QLabel("Waveform Templates"))
        layout.addLayout(form)
        layout.addWidget(self.apply_button)
        layout.addStretch(1)

    def set_project(self, project: Project) -> None:
        self.project = project

    def _channel_changed(self) -> None:
        self.channel = CHANNELS[self.channel_box.currentIndex()]
        self.channelChanged.emit(self.channel)

    def _apply(self) -> None:
        name = self.template_box.currentText()
        amplitude = self.amplitude.value()
        width = self.width.value()
        frequency = self.frequency.value()
        duty = self.duty.value()
        cycles = self.cycles.value()
        mapping: dict[str, Callable[[], object]] = {
            "Pulse": lambda: generators.pulse(amplitude=amplitude, width=width),
            "Double Pulse": lambda: generators.double_pulse(amplitude=amplitude, width=width),
            "Triangle": lambda: generators.triangle(amplitude=amplitude, period=width, cycles=cycles),
            "Ramp": lambda: generators.ramp(start_voltage=0.0, stop_voltage=amplitude, duration=width),
            "Sine": lambda: generators.sine(amplitude=amplitude, frequency=frequency, cycles=cycles),
            "Pulse Train": lambda: generators.pulse_train(
                amplitude=amplitude, frequency=frequency, duty_cycle=duty, cycles=cycles
            ),
            "Read/Write Pulse": lambda: generators.read_write_pulse(write_voltage=amplitude, read_voltage=amplitude / 10.0),
            "Custom": lambda: [],
        }
        next_project = self.project.clone()
        next_project.waveforms[self.channel] = list(mapping[name]())
        next_project.sort_waveforms()
        self.projectChanged.emit(next_project)
