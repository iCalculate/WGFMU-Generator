"""WGFMU Designer application entry point."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import PySide6
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from gui.main_window import MainWindow


def configure_qt_plugin_path() -> None:
    """Point Qt at PySide6's bundled plugins before QApplication exists.

    Some Anaconda/Windows installations report `site-packages/plugins` as the
    Qt plugin path even though PySide6 ships plugins under
    `site-packages/PySide6/plugins`. Without this bootstrap, Qt cannot find the
    `platforms/qwindows.dll` backend and the application exits at startup.
    """

    pyside_dir = Path(PySide6.__file__).resolve().parent
    plugins_dir = pyside_dir / "plugins"
    platforms_dir = plugins_dir / "platforms"
    if platforms_dir.exists():
        os.environ.setdefault("QT_PLUGIN_PATH", str(plugins_dir))
        os.environ.setdefault("QT_QPA_PLATFORM_PLUGIN_PATH", str(platforms_dir))
        QCoreApplication.addLibraryPath(str(plugins_dir))


def main() -> int:
    """Start the desktop application."""

    configure_qt_plugin_path()
    app = QApplication(sys.argv)
    app.setApplicationName("WGFMU Designer")
    app.setOrganizationName("WGFMU Designer")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
