"""Automatic WGFMU validation engine."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from core.models import CHANNELS, Project


@dataclass(frozen=True)
class ValidationMessage:
    """One validation result."""

    severity: str
    message: str


class WGFMUValidator:
    """Validate waveform vectors and measurement events against WGFMU rules."""

    def validate(self, project: Project) -> list[ValidationMessage]:
        messages: list[ValidationMessage] = []
        messages.extend(self._validate_waveforms(project))
        messages.extend(self._validate_measurements(project))
        messages.extend(self._validate_total_points(project))
        return messages

    def _validate_waveforms(self, project: Project) -> list[ValidationMessage]:
        messages: list[ValidationMessage] = []
        ranges = {
            "ch1": abs(project.settings.vforce_range_ch1),
            "ch2": abs(project.settings.vforce_range_ch2),
        }
        for channel in CHANNELS:
            points = project.waveforms[channel]
            if not points:
                messages.append(ValidationMessage("error", f"{channel.upper()} waveform is empty."))
                continue

            times = np.array([point.time for point in points], dtype=float)
            voltages = np.array([point.voltage for point in points], dtype=float)
            if np.any(np.diff(times) <= 0):
                messages.append(
                    ValidationMessage(
                        "error",
                        f"{channel.upper()} waveform time must be strictly monotonic.",
                    )
                )
            if np.any(np.abs(voltages) > ranges[channel]):
                messages.append(
                    ValidationMessage(
                        "error",
                        f"{channel.upper()} voltage exceeds VForceRange (+/-{ranges[channel]:g} V).",
                    )
                )
            if np.any(times < 0):
                messages.append(ValidationMessage("error", f"{channel.upper()} contains negative time values."))
        return messages

    def _validate_measurements(self, project: Project) -> list[ValidationMessage]:
        messages: list[ValidationMessage] = []
        duration = project.duration()
        all_times = sorted(
            point.time for channel in CHANNELS for point in project.waveforms[channel]
        )
        guard = project.settings.range_switch_guard_s

        for index, event in enumerate(project.measurements, start=1):
            prefix = f"Measurement row {index}:"
            if event.points < 0:
                messages.append(ValidationMessage("error", f"{prefix} Points cannot be negative."))
            if event.interval < 0:
                messages.append(ValidationMessage("error", f"{prefix} Interval cannot be negative."))
            if event.averaging > event.interval:
                messages.append(ValidationMessage("error", f"{prefix} Averaging is greater than Interval."))
            if event.tm < 0 or event.tm > duration:
                messages.append(ValidationMessage("error", f"{prefix} event starts outside waveform duration."))
            if event.points and event.interval:
                end_time = event.tm + max(0, event.points - 1) * event.interval
                if end_time > duration:
                    messages.append(
                        ValidationMessage("warning", f"{prefix} measurement extends beyond waveform duration.")
                    )
            if guard > 0 and any(abs(event.tm - t) < guard for t in all_times):
                messages.append(
                    ValidationMessage(
                        "warning",
                        f"{prefix} measurement starts within {guard:g} s of a waveform/range switch.",
                    )
                )

        if project.settings.repeat_count <= 0:
            messages.append(ValidationMessage("error", "RepeatCount must be a positive integer."))
        return messages

    def _validate_total_points(self, project: Project) -> list[ValidationMessage]:
        total = project.total_measurement_points()
        limit = project.active_point_limit()
        if total > limit:
            return [
                ValidationMessage(
                    "error",
                    f"Total measurement points {total} exceed WGFMU limit {limit}.",
                )
            ]
        return []
