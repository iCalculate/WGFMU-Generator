"""Engineering notation parsing and formatting helpers."""

from __future__ import annotations

import re


SI_PREFIXES = {
    "f": 1e-15,
    "p": 1e-12,
    "n": 1e-9,
    "u": 1e-6,
    "µ": 1e-6,
    "μ": 1e-6,
    "m": 1e-3,
    "": 1.0,
    "k": 1e3,
    "K": 1e3,
    "M": 1e6,
    "G": 1e9,
    "T": 1e12,
}

FORMAT_PREFIXES = [
    (1e12, "T"),
    (1e9, "G"),
    (1e6, "M"),
    (1e3, "k"),
    (1.0, ""),
    (1e-3, "m"),
    (1e-6, "u"),
    (1e-9, "n"),
    (1e-12, "p"),
    (1e-15, "f"),
]


def parse_si(text: str) -> float:
    """Parse floats with optional SI prefixes, e.g. `1n`, `2.5u`, `10k`.

    Scientific notation remains supported, so `2E-05` and `20u` both parse to
    the same value. Unit suffixes after the prefix are ignored: `1us`, `1u s`
    and `1u` are equivalent.
    """

    value = text.strip().replace(" ", "")
    if not value:
        raise ValueError("empty value")

    match = re.fullmatch(r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)([fpnuµμmkKMGTP]?)(?:[A-Za-z%]*)?", value)
    if not match:
        raise ValueError(f"invalid engineering value: {text}")
    number, prefix = match.groups()
    prefix = prefix.strip()
    if prefix not in SI_PREFIXES:
        raise ValueError(f"unsupported SI prefix: {prefix}")
    return float(number) * SI_PREFIXES[prefix]


def format_si(value: float, unit: str = "", precision: int = 4) -> str:
    """Format a value using a compact engineering prefix."""

    value = float(value)
    if value == 0:
        return f"0 {unit}".rstrip()
    abs_value = abs(value)
    for scale, prefix in FORMAT_PREFIXES:
        scaled = value / scale
        if abs_value >= scale or scale == FORMAT_PREFIXES[-1][0]:
            return f"{scaled:.{precision}g} {prefix}{unit}".rstrip()
    return f"{value:.{precision}g} {unit}".rstrip()
