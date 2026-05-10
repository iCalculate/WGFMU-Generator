"""WGFMU text export dialog."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QPushButton,
    QPlainTextEdit,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.models import Project
from exporters import wgfmu_exporter


class ExportDialog(QDialog):
    """Preview, copy and save Pattern Editor compatible text."""

    def __init__(self, project: Project, parent=None) -> None:
        super().__init__(parent)
        self.project = project
        self.setWindowTitle("Export WGFMU Text")
        self.resize(820, 620)

        self.tabs = QTabWidget()
        self.texts: dict[str, QPlainTextEdit] = {}
        for label, text in {
            "CH1": wgfmu_exporter.waveform_text(project, "ch1"),
            "CH2": wgfmu_exporter.waveform_text(project, "ch2"),
            "Measurement": wgfmu_exporter.measurement_text(project),
            "Combined": wgfmu_exporter.combined_text(project),
        }.items():
            editor = QPlainTextEdit(text)
            editor.setLineWrapMode(QPlainTextEdit.NoWrap)
            self.texts[label] = editor
            page = QWidget()
            page_layout = QVBoxLayout(page)
            page_layout.addWidget(editor)
            self.tabs.addTab(page, label)

        copy_button = QPushButton("Copy to Clipboard")
        save_button = QPushButton("Export to TXT")
        close_button = QPushButton("Close")
        copy_button.clicked.connect(self._copy)
        save_button.clicked.connect(self._save)
        close_button.clicked.connect(self.accept)

        buttons = QHBoxLayout()
        buttons.addWidget(copy_button)
        buttons.addWidget(save_button)
        buttons.addStretch(1)
        buttons.addWidget(close_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)
        layout.addLayout(buttons)

    def _current_text(self) -> str:
        label = self.tabs.tabText(self.tabs.currentIndex())
        text = self.texts[label].toPlainText().replace("\n", "\r\n").rstrip("\r\n")
        return text + "\r\n\r\n"

    def _copy(self) -> None:
        QApplication.clipboard().setText(self._current_text())

    def _save(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export WGFMU Text", "wgfmu_export.txt", "Text Files (*.txt)")
        if path:
            with open(path, "w", encoding="utf-8", newline="") as handle:
                handle.write(self._current_text())
