"""Live validation display."""

from __future__ import annotations

from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from validators.wgfmu_validator import ValidationMessage


class ValidationPanel(QWidget):
    """Shows validation warnings/errors and measurement point counter."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.counter = QLabel("Total Points: 0 / 20001")
        self.list_widget = QListWidget()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(self.counter)
        layout.addWidget(self.list_widget)

    def set_results(self, messages: list[ValidationMessage], total: int, limit: int) -> None:
        """Replace the displayed validation results."""

        self.counter.setText(f"Total Points: {total} / {limit}")
        self.list_widget.clear()
        if not messages:
            self.list_widget.addItem("No validation issues.")
            return
        for message in messages:
            item = QListWidgetItem(f"{message.severity.upper()}: {message.message}")
            if message.severity == "error":
                item.setForeground(QBrush(QColor("#ff5c66")))
            else:
                item.setForeground(QBrush(QColor("#ffd166")))
            self.list_widget.addItem(item)
