"""Application data model for WGFMU Designer.

The GUI edits these plain dataclasses and emits copies into the undo stack.
Keeping the model independent from Qt makes project files, exporters and
validators easy to test without creating a QApplication.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np


CHANNELS = ("ch1", "ch2")
FORCE_RANGE_OPTIONS = {
    "pm3": ("+/-3 V", -3.0, 3.0),
    "pm5": ("+/-5 V", -5.0, 5.0),
    "0_10": ("0 to 10 V", 0.0, 10.0),
    "neg10_0": ("-10 to 0 V", -10.0, 0.0),
}


@dataclass
class WaveformPoint:
    """One WGFMU vector point."""

    time: float
    voltage: float


@dataclass
class MeasurementEvent:
    """One measurement timing event row."""

    tm: float = 0.0
    points: int = 1
    interval: float = 1e-6
    averaging: float = 1e-6
    ch1_range: float = 0.0
    ch2_range: float = 0.0


@dataclass
class ProjectSettings:
    """Validation/export settings that affect WGFMU limits."""

    name: str = "Untitled"
    repeat_count: int = 1
    runvector_limit: int = 20001
    visualization_limit: int = 5001
    waveform_timing_visualization: bool = False
    snap_enabled: bool = True
    snap_time: float = 0.0
    snap_voltage: float = 0.01
    smart_snap_enabled: bool = True
    sample_marker_mode: str = "adaptive"
    show_sample_points: bool = True
    waveform_display_mode: str = "overlay"
    minimum_point_spacing: float = 100e-9
    vforce_range_ch1: float = 10.0
    vforce_range_ch2: float = 10.0
    force_range_mode_ch1: str = "pm5"
    force_range_mode_ch2: str = "pm5"
    range_switch_guard_s: float = 1e-6
    measurement_sampling_interval: float = 1e-6


@dataclass
class Project:
    """Full project payload."""

    settings: ProjectSettings = field(default_factory=ProjectSettings)
    waveforms: dict[str, list[WaveformPoint]] = field(
        default_factory=lambda: {
            "ch1": [WaveformPoint(0.0, 0.0), WaveformPoint(1e-3, 0.0)],
            "ch2": [WaveformPoint(0.0, 0.0), WaveformPoint(1e-3, 0.0)],
        }
    )
    measurements: list[MeasurementEvent] = field(default_factory=list)

    def clone(self) -> "Project":
        """Return a deep copy through the JSON-compatible dict form."""

        return Project.from_dict(self.to_dict())

    def sort_waveforms(self) -> None:
        """Sort waveform vectors by time in-place."""

        for channel in CHANNELS:
            self.waveforms[channel].sort(key=lambda point: point.time)

    def enforce_monotonic_waveforms(self, minimum_step: float | None = None) -> None:
        """Sort waveforms and repair duplicate/non-increasing time values.

        WGFMU Pattern Editor expects strictly increasing time values. Interactive
        snapping can otherwise collapse multiple points onto the same timestamp,
        producing paste data such as repeated `0  0` rows.
        """

        step = minimum_step if minimum_step and minimum_step > 0 else self.settings.minimum_point_spacing
        for channel in CHANNELS:
            self.waveforms[channel] = make_monotonic_points(self.waveforms[channel], step)

    def enforce_force_ranges(self) -> None:
        """Clamp waveform voltages to the selected per-channel force ranges."""

        for channel in CHANNELS:
            low, high = force_range_limits(self.settings, channel)
            self.waveforms[channel] = [
                WaveformPoint(point.time, min(high, max(low, point.voltage)))
                for point in self.waveforms[channel]
            ]

    def duration(self) -> float:
        """Return the largest waveform time across channels."""

        values: list[float] = []
        for channel in CHANNELS:
            values.extend(point.time for point in self.waveforms.get(channel, []))
        return max(values) if values else 0.0

    def total_measurement_points(self) -> int:
        """WGFMU total measurement point count including repeat count."""

        return int(self.settings.repeat_count * sum(event.points for event in self.measurements))

    def active_point_limit(self) -> int:
        """Return the currently applicable WGFMU measurement point limit."""

        if self.settings.waveform_timing_visualization:
            return self.settings.visualization_limit
        return self.settings.runvector_limit

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""

        return {
            "settings": asdict(self.settings),
            "waveforms": {
                channel: [asdict(point) for point in self.waveforms.get(channel, [])]
                for channel in CHANNELS
            },
            "measurements": [asdict(event) for event in self.measurements],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Project":
        """Create a Project from a JSON-compatible dict."""

        settings = ProjectSettings(**payload.get("settings", {}))
        raw_waveforms = payload.get("waveforms", {})
        waveforms = {
            channel: [
                WaveformPoint(float(item["time"]), float(item["voltage"]))
                for item in raw_waveforms.get(channel, [])
            ]
            for channel in CHANNELS
        }
        measurements = [
            MeasurementEvent(
                tm=float(item.get("tm", 0.0)),
                points=int(item.get("points", 1)),
                interval=float(item.get("interval", 1e-6)),
                averaging=float(item.get("averaging", 0.0)),
                ch1_range=float(item.get("ch1_range", 0.0)),
                ch2_range=float(item.get("ch2_range", 0.0)),
            )
            for item in payload.get("measurements", [])
        ]
        project = cls(settings=settings, waveforms=waveforms, measurements=measurements)
        project.sort_waveforms()
        return project


def force_range_limits(settings: ProjectSettings, channel: str) -> tuple[float, float]:
    """Return the selected voltage force range limits for one channel."""

    key = settings.force_range_mode_ch1 if channel == "ch1" else settings.force_range_mode_ch2
    if key in FORCE_RANGE_OPTIONS:
        _label, low, high = FORCE_RANGE_OPTIONS[key]
        return low, high
    fallback = abs(settings.vforce_range_ch1 if channel == "ch1" else settings.vforce_range_ch2)
    return -fallback, fallback


def points_to_arrays(points: list[WaveformPoint]) -> tuple[np.ndarray, np.ndarray]:
    """Convert point objects into x/y arrays for pyqtgraph."""

    if not points:
        return np.array([], dtype=float), np.array([], dtype=float)
    return (
        np.array([point.time for point in points], dtype=float),
        np.array([point.voltage for point in points], dtype=float),
    )


def arrays_to_points(times: np.ndarray, voltages: np.ndarray) -> list[WaveformPoint]:
    """Convert x/y arrays into sorted waveform points."""

    points = [WaveformPoint(float(t), float(v)) for t, v in zip(times, voltages)]
    points.sort(key=lambda point: point.time)
    return points


def make_monotonic_points(points: list[WaveformPoint], minimum_step: float = 1e-12) -> list[WaveformPoint]:
    """Return points sorted by time with a fixed (0, 0) start."""

    ordered = sorted(points, key=lambda point: point.time)
    step = minimum_step if minimum_step > 0 else 1e-12
    fixed: list[WaveformPoint] = [WaveformPoint(0.0, 0.0)]
    last_time = 0.0
    for point in ordered:
        time_value = max(0.0, float(point.time))
        voltage = float(point.voltage)
        if time_value == 0.0 and voltage == 0.0:
            continue
        if time_value <= last_time:
            time_value = last_time + step
        fixed.append(WaveformPoint(time_value, voltage))
        last_time = time_value
    return fixed
