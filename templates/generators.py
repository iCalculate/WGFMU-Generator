"""Waveform generator functions used by the template panel."""

from __future__ import annotations

import math

import numpy as np

from core.models import WaveformPoint


def _strict(points: list[WaveformPoint], epsilon: float = 1e-15) -> list[WaveformPoint]:
    """Return points sorted with duplicate times nudged forward for WGFMU vectors."""

    ordered = sorted(points, key=lambda point: point.time)
    last_time = -float("inf")
    fixed: list[WaveformPoint] = []
    for point in ordered:
        time_value = point.time if point.time > last_time else last_time + epsilon
        fixed.append(WaveformPoint(time_value, point.voltage))
        last_time = time_value
    return fixed


def pulse(
    amplitude: float = 1.0,
    hold: float = 1e-3,
    rise: float = 1e-6,
    fall: float = 1e-6,
    delay: float = 0.0,
    total: float | None = None,
) -> list[WaveformPoint]:
    """Generate a single trapezoidal pulse."""

    start = max(0.0, delay)
    rise = max(0.0, rise)
    hold = max(0.0, hold)
    fall = max(0.0, fall)
    end = start + rise + hold + fall
    total_time = max(end, total if total is not None else end)
    points = [WaveformPoint(0.0, 0.0)]
    if start > 0.0:
        points.append(WaveformPoint(start, 0.0))
    points.extend(
        [
            WaveformPoint(start + rise, amplitude),
            WaveformPoint(start + rise + hold, amplitude),
            WaveformPoint(end, 0.0),
        ]
    )
    if total_time > end:
        points.append(WaveformPoint(total_time, 0.0))
    return _strict(points)


def double_pulse(
    amplitude1: float = 1.0,
    hold1: float = 1e-3,
    rise1: float = 1e-6,
    fall1: float = 1e-6,
    delay1: float = 0.0,
    amplitude2: float = 1.0,
    hold2: float = 1e-3,
    rise2: float = 1e-6,
    fall2: float = 1e-6,
    delay2: float = 2e-3,
    total: float | None = None,
) -> list[WaveformPoint]:
    """Generate two independently parameterized trapezoidal pulses."""

    first = pulse(amplitude=amplitude1, hold=hold1, rise=rise1, fall=fall1, delay=delay1)
    second = [
        point
        for point in pulse(amplitude=amplitude2, hold=hold2, rise=rise2, fall=fall2, delay=delay2)
        if point.time > 0.0
    ]
    end = max([point.time for point in first + second], default=0.0)
    total_time = max(end, total if total is not None else end)
    points = first + second
    if total_time > end:
        points.append(WaveformPoint(total_time, 0.0))
    return _strict(points)


def pulse_train(amplitude: float = 1.0, frequency: float = 1_000.0,
                duty_cycle: float = 50.0, cycles: int = 5) -> list[WaveformPoint]:
    """Generate a rectangular pulse train."""

    frequency = max(frequency, 1e-30)
    cycles = max(1, int(cycles))
    duty = min(100.0, max(0.0, duty_cycle)) / 100.0
    period = 1.0 / frequency
    high_time = duty * period
    points = [WaveformPoint(0.0, 0.0)]
    for i in range(cycles):
        start = i * period
        points.extend(
            [
                WaveformPoint(start, amplitude),
                WaveformPoint(start + high_time, amplitude),
                WaveformPoint(start + high_time, 0.0),
                WaveformPoint(start + period, 0.0),
            ]
        )
    return _strict(points)


def triangle(amplitude: float = 1.0, period: float = 1e-3, cycles: int = 2) -> list[WaveformPoint]:
    """Generate a triangle waveform."""

    cycles = max(1, int(cycles))
    points = []
    for i in range(cycles):
        base = i * period
        points.extend(
            [
                WaveformPoint(base, -amplitude),
                WaveformPoint(base + period / 2.0, amplitude),
                WaveformPoint(base + period, -amplitude),
            ]
        )
    return _strict(points)


def ramp(start_voltage: float = 0.0, stop_voltage: float = 1.0,
         duration: float = 1e-3, samples: int = 100) -> list[WaveformPoint]:
    """Generate a linear ramp."""

    samples = max(2, int(samples))
    times = np.linspace(0.0, duration, samples)
    voltages = np.linspace(start_voltage, stop_voltage, samples)
    return [WaveformPoint(float(t), float(v)) for t, v in zip(times, voltages)]


def sine(amplitude: float = 1.0, frequency: float = 1_000.0,
         cycles: int = 2, samples_per_cycle: int = 100) -> list[WaveformPoint]:
    """Generate a sine wave."""

    frequency = max(frequency, 1e-30)
    cycles = max(1, int(cycles))
    samples = max(8, int(samples_per_cycle) * cycles)
    duration = cycles / frequency
    times = np.linspace(0.0, duration, samples)
    voltages = amplitude * np.sin(2.0 * math.pi * frequency * times)
    return [WaveformPoint(float(t), float(v)) for t, v in zip(times, voltages)]


def read_write_pulse(write_voltage: float = 2.0, read_voltage: float = 0.2,
                     width: float = 1e-3, read_delay: float = 2e-3) -> list[WaveformPoint]:
    """Generate a simple write pulse followed by a read pulse."""

    return [
        WaveformPoint(0.0, 0.0),
        WaveformPoint(1e-6, write_voltage),
        WaveformPoint(width, write_voltage),
        WaveformPoint(width + 1e-6, 0.0),
        WaveformPoint(read_delay, 0.0),
        WaveformPoint(read_delay + 1e-6, read_voltage),
        WaveformPoint(read_delay + width, read_voltage),
        WaveformPoint(read_delay + width + 1e-6, 0.0),
    ]
