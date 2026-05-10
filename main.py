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
    PyInstaller one-file builds unpack PySide6 into `sys._MEIPASS`, so frozen
    candidates must be checked explicitly as well.
    """

    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        bundle_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        candidates.extend(
            [
                bundle_dir / "PySide6" / "plugins",
                bundle_dir / "PySide6" / "Qt" / "plugins",
                bundle_dir / "plugins",
            ]
        )
        # PyInstaller hook layouts vary by PySide6 version. A shallow fallback
        # keeps the EXE resilient without hardcoding one exact internal layout.
        try:
            candidates.extend(path.parent.parent for path in bundle_dir.glob("**/platforms/qwindows.dll"))
        except OSError:
            pass

    pyside_dir = Path(PySide6.__file__).resolve().parent
    candidates.extend([pyside_dir / "plugins", pyside_dir / "Qt" / "plugins"])

    for plugins_dir in candidates:
        platforms_dir = plugins_dir / "platforms"
        if platforms_dir.exists():
            os.environ["QT_PLUGIN_PATH"] = str(plugins_dir)
            os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(platforms_dir)
            QCoreApplication.addLibraryPath(str(plugins_dir))
            if hasattr(os, "add_dll_directory"):
                try:
                    os.add_dll_directory(str(Path(PySide6.__file__).resolve().parent))
                except OSError:
                    pass
            break


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
