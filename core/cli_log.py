"""Small colored CLI logger shared by the desktop app."""

from __future__ import annotations

import os
import sys
from datetime import datetime


ANSI = {
    "reset": "\033[0m",
    "dim": "\033[2m",
    "cyan": "\033[96m",
    "green": "\033[92m",
    "yellow": "\033[93m",
    "red": "\033[91m",
    "magenta": "\033[95m",
}

LOGO = r"""
 __        ______ _____ __  __ _   _
 \ \      / / ___|  ___|  \/  | | | |
  \ \ /\ / / |  _| |_  | |\/| | | | |
   \ V  V /| |_| |  _| | |  | | |_| |
    \_/\_/  \____|_|   |_|  |_|\___/

        D E S I G N E R
"""


def _supports_color() -> bool:
    if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
        return False
    if os.name != "nt":
        return True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        return bool(kernel32.SetConsoleMode(handle, mode.value | 0x0004))
    except Exception:
        return False


USE_COLOR = _supports_color()


def color(text: str, name: str) -> str:
    if not USE_COLOR:
        return text
    return f"{ANSI[name]}{text}{ANSI['reset']}"


def print_banner() -> None:
    print(color(LOGO, "cyan"))
    print(color("  Keysight B1500A / B1530A WGFMU waveform editor", "dim"))
    print()


def log(level: str, message: str, *, detail: str | None = None) -> None:
    palette = {
        "INFO": "cyan",
        "OK": "green",
        "WARN": "yellow",
        "ERROR": "red",
        "DEBUG": "magenta",
    }
    label = color(f"[{level:<5}]", palette.get(level, "cyan"))
    timestamp = color(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "dim")
    print(f"{timestamp} {label} {message}", flush=True)
    if detail:
        print(color(f"{'':19} {'':7} {detail}", "dim"), flush=True)
