"""WGFMU Designer application entry point."""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

import PySide6
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from core.cli_log import color, log, print_banner
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
            log("OK", "Qt plugin path configured", detail=str(plugins_dir))
            break
    else:
        log("WARN", "Qt plugin path was not found explicitly; using Qt defaults")


def main() -> int:
    """Start the desktop application."""

    print_banner()
    log("INFO", "Starting WGFMU Designer")
    configure_qt_plugin_path()
    log("INFO", "Creating Qt application")
    app = QApplication(sys.argv)
    app.setApplicationName("WGFMU Designer")
    app.setOrganizationName("WGFMU Designer")
    log("INFO", "Building main window")
    window = MainWindow()
    window.show()
    log("OK", "GUI is ready")
    exit_code = app.exec()
    log("INFO", "Application exited", detail=f"exit_code={exit_code}")
    return exit_code


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        log("ERROR", f"Startup failed: {exc}")
        print(color(traceback.format_exc(), "red"))
        raise
