"""WGFMU Pattern Editor text exporters."""

from __future__ import annotations

from pathlib import Path

from core.models import CHANNELS, Project, make_monotonic_points


LINE_ENDING = "\r\n"


def _fmt(value: float) -> str:
    """Compact numeric formatting accepted by the WGFMU Pattern Editor."""

    return f"{float(value):.12G}"


def waveform_text(project: Project, channel: str) -> str:
    """Export one channel as tab-separated `time voltage` rows."""

    step = project.settings.minimum_point_spacing if project.settings.minimum_point_spacing > 0 else 1e-12
    points = make_monotonic_points(project.waveforms[channel], minimum_step=step)
    rows = [f"{_fmt(point.time)}\t{_fmt(point.voltage)}" for point in points]
    return with_paste_terminator(LINE_ENDING.join(rows))


def measurement_text(project: Project) -> str:
    """Export measurement rows in WGFMU Pattern Editor order."""

    rows = []
    for event in project.measurements:
        rows.append(
            "\t".join(
                [
                    _fmt(event.tm),
                    str(int(event.points)),
                    _fmt(event.interval),
                    _fmt(event.averaging),
                    _fmt(event.ch1_range),
                    _fmt(event.ch2_range),
                ]
            )
        )
    return with_paste_terminator(LINE_ENDING.join(rows))


def combined_text(project: Project) -> str:
    """Export a readable text bundle containing both waveforms and measurements."""

    sections = []
    for channel in CHANNELS:
        sections.append(f"# {channel.upper()} Waveform")
        sections.append(waveform_text(project, channel))
        sections.append("")
    sections.append("# Measurement Events")
    sections.append(measurement_text(project))
    return with_paste_terminator(LINE_ENDING.join(sections).rstrip())


def with_paste_terminator(text: str) -> str:
    """Return text with an extra trailing blank line for WGFMU paste."""

    stripped = text.rstrip("\r\n")
    if not stripped:
        return LINE_ENDING + LINE_ENDING
    return stripped + LINE_ENDING + LINE_ENDING


def save_text(path: str | Path, project: Project) -> None:
    """Write the combined WGFMU text bundle."""

    Path(path).write_text(combined_text(project), encoding="utf-8")
