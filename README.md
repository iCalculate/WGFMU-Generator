# WGFMU Designer

WGFMU Designer is a desktop waveform and measurement-event editor for Keysight B1500A / B1530A WGFMU Pattern Editor workflows.

## Features

- Dual-channel waveform editing for CH1 and CH2
- Interactive `pyqtgraph` waveform display with zoom, pan, cursor readout, grid, selectable points/segments, and modifier-based editing
- Dragging a point previews continuously but creates one undo step only after mouse release
- Left-side Editor panel controls for active edit channel, Auto Y, Auto XY, sample point display, and overlay/stacked channel display
- On-plot minimum/median sample interval readout for each channel
- Real-time graph coordinate readout while moving the cursor or dragging a point
- Sample point display modes: adaptive points, all points, or hidden points
- Selected waveform point highlight remains visible even when normal sample points are hidden
- Minimum point spacing defaults to `100 ns` for sharp edges and near-overlapping time points
- Measurement event table with editable `tm`, `Points`, `Interval`, `Averaging`, `Ch1 Range`, and `Ch2 Range`
- Live WGFMU validation and total measurement point counter
- Waveform generators: pulse, double pulse, triangle, ramp, sine, pulse train, read/write pulse, and custom blank waveform
- WGFMU Pattern Editor tab-separated text preview, clipboard copy, and TXT export
- JSON project save/load
- CSV export for waveforms and CSV import/export for measurement events
- Undo/redo with `Ctrl+Z` and `Ctrl+Y`
- Dark EDA/oscilloscope-style PySide6 interface with dockable panels

## Install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run

```powershell
python main.py
```

## Keyboard Shortcuts

- `Ctrl+N`: new project
- `Ctrl+O`: open project
- `Ctrl+S`: save project
- `Ctrl+Z`: undo
- `Ctrl+Y`: redo

## Editing Notes

The editor snaps dragged and inserted points to `Snap Time` and `Snap Voltage`
when snapping is enabled. Use simple values such as `1e-6` seconds and `0.01`
volts to keep edited coordinates clean and integer-like. Setting `Snap Time` to
`0` enables smart nice-number snapping based on the current view range.

Click a waveform point or segment to select it. Use `Ctrl+Click` to add a point
to the active channel, `Alt+Click` near a point to delete it,
and hold `Shift` while dragging to move points or selected segments.

## WGFMU Text Export

Waveform rows are exported as tab-separated values:

```text
time	voltage
```

Measurement rows are exported as:

```text
tm	Points	Interval	Averaging	Ch1 Range	Ch2 Range
```

`Ch1 Range` and `Ch2 Range` are WGFMU range-event columns and default to `0`,
which leaves the normal current measurement range unchanged. Set a value from
`1` to `5` only when a range event is needed: `1 = 1 uA`, `2 = 10 uA`,
`3 = 100 uA`, `4 = 1 mA`, and `5 = 10 mA`.

In the plot, right-drag across the waveform to create a measurement time range.
The drag endpoints follow the time snap setting and the highlighted background
area stays synchronized with the measurement table. Use `Alt+Right Drag` to
remove part of an existing measurement range; this can split one table row into
two rows when the removed time window is in the middle.

The measurement panel sampling buttons (`10n` through `1s`) set the default
`Interval` and `Averaging` for measurement ranges or rows created after the
selection changes. Existing measurement rows are not modified.

Numeric template fields accept engineering prefixes such as `1n`, `20u`,
`1m`, `1k`, `2.5M`, and scientific notation such as `2E-05`.

For direct paste into Keysight WGFMU Pattern Editor, waveform time values must
be strictly increasing. Repeated rows such as `0	0` four times are invalid; the
application repairs duplicate timestamps during graph editing and text export.
Exported text uses tab-separated columns and includes an extra trailing blank
line because WGFMU Pattern Editor paste recognition is sensitive to the final
line terminator.

The export dialog has separate tabs for CH1, CH2, measurement events, and a combined annotated text bundle.

## Validation Rules

The live validator reports:

- Empty waveforms
- Non-monotonic or duplicate waveform time
- Negative interval
- Averaging greater than interval
- Voltage exceeding per-channel `VForceRange`
- Total measurement points over WGFMU limits
- Measurement start too close to waveform/range switches
- Invalid repeat count
- Measurement event outside waveform duration

When `RepeatCount` is greater than `1`, the plot shows repeated cycles after
the editable first cycle as low-contrast line-only waveforms. Waveform and
measurement edits are limited to the first cycle.

Channel force range is selected from fixed ranges: `+/-3 V`, `+/-5 V`,
`0 to 10 V`, and `-10 to 0 V`. Waveform voltages are clamped to the selected
range and validation reports any out-of-range data.

Total measurement points are calculated as:

```text
RepeatCount * sum(Points)
```

Limits:

- `20001` for normal RunVector
- `5001` when waveform timing visualization is enabled

## Build Windows EXE

Install dependencies first, then run:

```powershell
pyinstaller --onefile --windowed --name "WGFMU Designer" main.py
```

The EXE will be created under `dist\WGFMU Designer.exe`.

If PyInstaller misses Qt plugins on a particular machine, rebuild with:

```powershell
pyinstaller --onefile --windowed --name "WGFMU Designer" --collect-all PySide6 --collect-all pyqtgraph main.py
```

## Project Structure

```text
core/        dataclasses and project/CSV IO
exporters/   WGFMU text exporters
gui/         main window and application shell
templates/   waveform generator functions
validators/  WGFMU validation engine
widgets/     reusable PySide6/pyqtgraph widgets
main.py      application entry point
```
