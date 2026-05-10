"""Line edit for numeric engineering/SI-prefix input."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLineEdit

from core.si_units import format_si, parse_si


class SIInput(QLineEdit):
    """Small numeric editor that accepts `1n`, `1u`, `1k`, and `1E-6`."""

    valueChanged = Signal(float)

    def __init__(
        self,
        value: float,
        minimum: float = -float("inf"),
        maximum: float = float("inf"),
        unit: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.minimum = minimum
        self.maximum = maximum
        self.unit = unit
        self._value = float(value)
        self.setPlaceholderText(f"e.g. 1n, 10u, 1k {unit}".strip())
        self.setText(format_si(self._value, unit=""))
        self.editingFinished.connect(self._commit_text)

    def value(self) -> float:
        """Return the committed numeric value."""

        return self._value

    def setValue(self, value: float) -> None:  # noqa: N802 - Qt naming style
        """Set and display the value."""

        self._value = self._clamp(float(value))
        self.setText(format_si(self._value, unit=""))
        self._set_valid(True)

    def _clamp(self, value: float) -> float:
        return min(self.maximum, max(self.minimum, value))

    def _commit_text(self) -> None:
        try:
            value = self._clamp(parse_si(self.text()))
        except ValueError:
            self._set_valid(False)
            return
        changed = value != self._value
        self._value = value
        self.setText(format_si(value, unit=""))
        self._set_valid(True)
        if changed:
            self.valueChanged.emit(value)

    def _set_valid(self, valid: bool) -> None:
        if valid:
            self.setStyleSheet("")
        else:
            self.setStyleSheet("border: 1px solid #ff5c66;")
