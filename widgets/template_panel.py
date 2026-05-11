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
            ["Single Pulse", "Double Pulse", "Triangle", "Ramp", "Sine", "Pulse Train", "Read/Write Pulse", "Custom"]
        )
        self.template_box.currentIndexChanged.connect(self._update_field_visibility)

        self.amplitude = SIInput(1.0, -200.0, 200.0, "V")
        self.width = SIInput(1e-3, 0.0, 1000.0, "s")
        self.frequency = SIInput(1000.0, 1e-9, 1e12, "Hz")
        self.duty = SIInput(50.0, 0.0, 100.0, "%")
        self.pulse_start = SIInput(0.0, 0.0, 1000.0, "s")
        self.pulse_rise = SIInput(1e-6, 0.0, 1000.0, "s")
        self.pulse_hold = SIInput(1e-3, 0.0, 1000.0, "s")
        self.pulse_fall = SIInput(1e-6, 0.0, 1000.0, "s")
        self.pulse_total = SIInput(1.002e-3, 0.0, 1000.0, "s")
        self.pulse2_start = SIInput(2e-3, 0.0, 1000.0, "s")
        self.pulse2_rise = SIInput(1e-6, 0.0, 1000.0, "s")
        self.pulse2_amplitude = SIInput(1.0, -200.0, 200.0, "V")
        self.pulse2_hold = SIInput(1e-3, 0.0, 1000.0, "s")
        self.pulse2_fall = SIInput(1e-6, 0.0, 1000.0, "s")
        self.cycles = QSpinBox()
        self.cycles.setRange(1, 100000)
        self.cycles.setValue(5)
        self.apply_button = QPushButton("Apply Template")
        self.apply_button.clicked.connect(self._apply)

        form = QFormLayout()
        form.addRow("Channel", self.channel_box)
        form.addRow("Template", self.template_box)
        self.amplitude_label = QLabel("Amplitude [V]")
        self.width_label = QLabel("Width/Duration [s]")
        self.frequency_label = QLabel("Frequency [Hz]")
        self.duty_label = QLabel("Duty [%]")
        self.cycles_label = QLabel("Cycles")
        form.addRow(self.amplitude_label, self.amplitude)
        form.addRow(self.width_label, self.width)
        self.pulse_rows = [
            ("P1 Rise Position [s]", self.pulse_start),
            ("P1 Rise Time [s]", self.pulse_rise),
            ("P1 Hold Time [s]", self.pulse_hold),
            ("P1 Fall Time [s]", self.pulse_fall),
            ("Total Time [s]", self.pulse_total),
        ]
        self.pulse2_rows = [
            ("P2 Rise Position [s]", self.pulse2_start),
            ("P2 Rise Time [s]", self.pulse2_rise),
            ("P2 Amplitude [V]", self.pulse2_amplitude),
            ("P2 Hold Time [s]", self.pulse2_hold),
            ("P2 Fall Time [s]", self.pulse2_fall),
        ]
        self._field_labels: dict[QWidget, QLabel] = {}
        for label_text, control in [*self.pulse_rows, *self.pulse2_rows]:
            label = QLabel(label_text)
            self._field_labels[control] = label
            form.addRow(label, control)
        form.addRow(self.frequency_label, self.frequency)
        form.addRow(self.duty_label, self.duty)
        form.addRow(self.cycles_label, self.cycles)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(QLabel("Waveform Templates"))
        layout.addLayout(form)
        layout.addWidget(self.apply_button)
        layout.addStretch(1)
        self._update_field_visibility()

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
            "Single Pulse": lambda: generators.pulse(
                amplitude=amplitude,
                hold=self.pulse_hold.value(),
                rise=self.pulse_rise.value(),
                fall=self.pulse_fall.value(),
                delay=self.pulse_start.value(),
                total=self.pulse_total.value(),
            ),
            "Double Pulse": lambda: generators.double_pulse(
                amplitude1=amplitude,
                hold1=self.pulse_hold.value(),
                rise1=self.pulse_rise.value(),
                fall1=self.pulse_fall.value(),
                delay1=self.pulse_start.value(),
                amplitude2=self.pulse2_amplitude.value(),
                hold2=self.pulse2_hold.value(),
                rise2=self.pulse2_rise.value(),
                fall2=self.pulse2_fall.value(),
                delay2=self.pulse2_start.value(),
                total=self.pulse_total.value(),
            ),
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

    def _update_field_visibility(self) -> None:
        name = self.template_box.currentText()
        pulse_visible = name in {"Single Pulse", "Double Pulse"}
        pulse2_visible = name == "Double Pulse"
        for _label_text, control in self.pulse_rows:
            self._set_field_visible(control, pulse_visible)
        for _label_text, control in self.pulse2_rows:
            self._set_field_visible(control, pulse2_visible)
        self._set_static_field_visible(self.width_label, self.width, not pulse_visible)
        self._set_static_field_visible(self.frequency_label, self.frequency, name in {"Sine", "Pulse Train"})
        self._set_static_field_visible(self.duty_label, self.duty, name == "Pulse Train")
        self._set_static_field_visible(self.cycles_label, self.cycles, name in {"Triangle", "Sine", "Pulse Train"})

    def _set_field_visible(self, control: QWidget, visible: bool) -> None:
        label = self._field_labels.get(control)
        if label is not None:
            label.setVisible(visible)
        control.setVisible(visible)

    def _set_static_field_visible(self, label: QLabel, control: QWidget, visible: bool) -> None:
        label.setVisible(visible)
        control.setVisible(visible)
