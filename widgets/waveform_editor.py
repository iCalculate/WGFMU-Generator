"""Interactive pyqtgraph waveform editor."""

from __future__ import annotations

from typing import Optional

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu

from core.models import CHANNELS, Project, WaveformPoint, points_to_arrays
from core.si_units import format_si


class DraggablePoint(pg.ScatterPlotItem):
    """Scatter points with drag/edit behavior for one channel."""

    dragStarted = Signal(str, int)
    pointDragged = Signal(str, int, float, float)
    dragFinished = Signal()
    pointDeleted = Signal(str, int)
    pointSelected = Signal(str, int)

    def __init__(self, channel: str, color: str) -> None:
        super().__init__(size=9, pen=pg.mkPen(color, width=1.4), brush=pg.mkBrush(color))
        self.channel = channel
        self._drag_index: Optional[int] = None

    def mouseDragEvent(self, event) -> None:  # noqa: N802 - pyqtgraph API
        if event.button() != Qt.LeftButton:
            event.ignore()
            return
        spots = self.pointsAt(event.buttonDownPos())
        if event.isStart():
            self._drag_index = int(spots[0].data()) if len(spots) else None
            if self._drag_index is not None:
                self.dragStarted.emit(self.channel, self._drag_index)
        if self._drag_index is not None:
            pos = event.pos()
            self.pointDragged.emit(self.channel, self._drag_index, float(pos.x()), float(pos.y()))
            event.accept()
        if event.isFinish():
            if self._drag_index is not None:
                self.dragFinished.emit()
            self._drag_index = None

    def mouseClickEvent(self, event) -> None:  # noqa: N802 - pyqtgraph API
        if event.button() == Qt.RightButton:
            spots = self.pointsAt(event.pos())
            if spots:
                self.pointDeleted.emit(self.channel, int(spots[0].data()))
                event.accept()
                return
        if event.button() == Qt.LeftButton:
            spots = self.pointsAt(event.pos())
            if spots:
                self.pointSelected.emit(self.channel, int(spots[0].data()))
                event.accept()
                return
        super().mouseClickEvent(event)


class WaveformEditor(pg.PlotWidget):
    """Main oscilloscope-like editor with two channels and timing overlays."""

    projectChanged = Signal(object)
    cursorChanged = Signal(float, float)

    COLORS = {"ch1": "#4ea1ff", "ch2": "#ff5c66"}

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        pg.setConfigOptions(antialias=True)
        self.project = Project()
        self.active_channel = "ch1"
        self._drag_project: Project | None = None
        self._drag_changed = False
        self.selected_point: tuple[str, int] | None = None
        self.sample_marker_mode = "adaptive"
        self.showGrid(x=True, y=True, alpha=0.28)
        self.setBackground("#11151c")
        self.setLabel("bottom", "Time", units="s")
        self.setLabel("left", "Voltage", units="V")
        self.addLegend(offset=(12, 12))
        self.getPlotItem().setMenuEnabled(False)
        self.getViewBox().setMouseMode(pg.ViewBox.PanMode)

        self.curves = {
            "ch1": self.plot([], [], pen=pg.mkPen(self.COLORS["ch1"], width=2.2), name="Ch1"),
            "ch2": self.plot([], [], pen=pg.mkPen(self.COLORS["ch2"], width=2.2), name="Ch2"),
        }
        self.points = {
            channel: DraggablePoint(channel, color)
            for channel, color in self.COLORS.items()
        }
        for item in self.points.values():
            item.dragStarted.connect(self._begin_drag_point)
            item.pointDragged.connect(self._preview_drag_point)
            item.dragFinished.connect(self._finish_drag_point)
            item.pointDeleted.connect(self._delete_point)
            item.pointSelected.connect(self._select_point)
            self.addItem(item)
        self.selected_marker = pg.ScatterPlotItem(
            size=16,
            pen=pg.mkPen("#ffffff", width=2.5),
            brush=pg.mkBrush(255, 209, 102, 90),
            symbol="o",
        )
        self.addItem(self.selected_marker, ignoreBounds=True)

        self.measurement_items: list[pg.InfiniteLine] = []
        self.cursor_line = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen("#cfd8dc", width=1, style=Qt.DashLine))
        self.addItem(self.cursor_line)
        self.sample_info = pg.TextItem(color="#cfd8dc", anchor=(0, 0))
        self.addItem(self.sample_info, ignoreBounds=True)
        self.cursor_info = pg.TextItem(color="#9fb2c3", anchor=(1, 0))
        self.addItem(self.cursor_info, ignoreBounds=True)
        self.drag_info = pg.TextItem(color="#ffffff", fill=pg.mkBrush(20, 25, 33, 210), anchor=(0, 1))
        self.drag_info.hide()
        self.addItem(self.drag_info, ignoreBounds=True)
        self.scene().sigMouseMoved.connect(self._mouse_moved)
        self.getViewBox().sigRangeChanged.connect(lambda *_args: self._position_overlay_text())

    def set_project(self, project: Project) -> None:
        """Replace the displayed project."""

        self.project = project
        self.sample_marker_mode = project.settings.sample_marker_mode
        self.refresh()

    def set_active_channel(self, channel: str) -> None:
        """Set the channel affected by add/context-menu actions."""

        if channel in CHANNELS:
            self.active_channel = channel

    def set_sample_marker_mode(self, mode: str) -> None:
        """Set point marker display mode: adaptive, all, or hidden."""

        self.sample_marker_mode = mode
        self.refresh()

    def refresh(self) -> None:
        """Redraw curves, handles and measurement overlays."""

        for channel in CHANNELS:
            x, y = points_to_arrays(self.project.waveforms[channel])
            self.curves[channel].setData(x, y)
            marker_x, marker_y, marker_indexes = self._marker_data(channel, x, y)
            self.points[channel].setData(x=marker_x, y=marker_y, data=marker_indexes)
        self._draw_measurement_overlays()
        self._update_selected_marker()
        self._update_sample_info()

    def _marker_data(self, channel: str, x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray, list[int]]:
        """Return marker data for the configured sample display mode."""

        if not self.project.settings.show_sample_points or self.sample_marker_mode == "hidden" or len(x) == 0:
            return np.array([], dtype=float), np.array([], dtype=float), []
        if self.sample_marker_mode == "all" or len(x) <= 400:
            return x, y, list(range(len(x)))

        # Adaptive mode keeps the editor readable for generated dense waveforms:
        # endpoints, voltage transition points and a bounded even sample.
        transition_indexes = set(np.where(np.diff(y) != 0)[0].tolist())
        transition_indexes.update((idx + 1 for idx in list(transition_indexes) if idx + 1 < len(x)))
        even_indexes = set(np.linspace(0, len(x) - 1, 300, dtype=int).tolist())
        indexes = sorted({0, len(x) - 1, *transition_indexes, *even_indexes})
        if len(indexes) > 700:
            indexes = sorted(set(np.linspace(0, len(x) - 1, 700, dtype=int).tolist()))
        return x[indexes], y[indexes], indexes

    def contextMenuEvent(self, event) -> None:  # noqa: N802 - Qt API
        scene_point = self.mapToScene(event.pos())
        point = self.getPlotItem().vb.mapSceneToView(scene_point)
        menu = QMenu(self)
        add = QAction(f"Add point to {self.active_channel.upper()}", self)
        select_nearest = QAction(f"Select nearest {self.active_channel.upper()} point", self)
        delete_nearest = QAction(f"Delete nearest {self.active_channel.upper()} point", self)
        sharp_up = QAction(f"Insert rising sharp edge ({self.active_channel.upper()})", self)
        sharp_down = QAction(f"Insert falling sharp edge ({self.active_channel.upper()})", self)
        auto_y = QAction("Auto Y Range", self)
        auto_xy = QAction("Auto XY Range", self)
        menu.addAction(add)
        menu.addAction(select_nearest)
        menu.addAction(delete_nearest)
        menu.addSeparator()
        menu.addAction(sharp_up)
        menu.addAction(sharp_down)
        menu.addSeparator()
        menu.addAction(auto_y)
        menu.addAction(auto_xy)
        chosen = menu.exec(event.globalPos())
        if chosen == add:
            self._add_point(self.active_channel, float(point.x()), float(point.y()))
        elif chosen == select_nearest:
            self._select_nearest(self.active_channel, float(point.x()))
        elif chosen == delete_nearest:
            self._delete_nearest(self.active_channel, float(point.x()))
        elif chosen == sharp_up:
            self._insert_sharp_edge(self.active_channel, float(point.x()), rising=True)
        elif chosen == sharp_down:
            self._insert_sharp_edge(self.active_channel, float(point.x()), rising=False)
        elif chosen == auto_y:
            self.auto_y_range()
        elif chosen == auto_xy:
            self.auto_xy_range()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 - Qt API
        if event.button() == Qt.LeftButton:
            scene_point = self.mapToScene(event.position().toPoint())
            point = self.getPlotItem().vb.mapSceneToView(scene_point)
            if event.modifiers() & Qt.ShiftModifier:
                self._insert_sharp_edge(self.active_channel, float(point.x()), rising=True)
            else:
                self._add_point(self.active_channel, float(point.x()), float(point.y()))
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API
        if event.button() == Qt.LeftButton and not (event.modifiers() & Qt.ShiftModifier):
            scene_point = self.mapToScene(event.position().toPoint())
            view_point = self.getPlotItem().vb.mapSceneToView(scene_point)
            if self._handle_segment_click(float(view_point.x()), float(view_point.y())):
                event.accept()
                return
        super().mousePressEvent(event)

    def _snap(self, time_value: float, voltage: float) -> tuple[float, float]:
        settings = self.project.settings
        if settings.snap_enabled:
            time_step = self._active_snap_time()
            voltage_step = self._active_snap_voltage()
            if time_step > 0:
                time_value = round(time_value / time_step) * time_step
            if voltage_step > 0:
                voltage = round(voltage / voltage_step) * voltage_step
        return max(0.0, time_value), voltage

    def _active_snap_time(self) -> float:
        settings = self.project.settings
        if settings.snap_time > 0:
            return settings.snap_time
        if not settings.smart_snap_enabled:
            return 0.0
        x_min, x_max = self.getViewBox().viewRange()[0]
        return self._integer_view_step((x_max - x_min) / 100.0)

    def _active_snap_voltage(self) -> float:
        settings = self.project.settings
        if settings.snap_voltage > 0:
            return settings.snap_voltage
        if not settings.smart_snap_enabled:
            return 0.0
        y_min, y_max = self.getViewBox().viewRange()[1]
        return self._integer_view_step((y_max - y_min) / 80.0)

    def _integer_view_step(self, raw_step: float) -> float:
        """Return a view-scaled 1/2/5 grid step with integer mantissa."""

        if raw_step <= 0:
            return 0.0
        exponent = np.floor(np.log10(raw_step))
        base = raw_step / (10 ** exponent)
        if base <= 1:
            nice = 1
        elif base <= 2:
            nice = 2
        elif base <= 5:
            nice = 5
        else:
            nice = 10
        return float(nice * (10 ** exponent))

    def auto_y_range(self) -> None:
        """Fit the Y axis to visible waveform voltages."""

        voltages = [
            point.voltage
            for channel in CHANNELS
            for point in self.project.waveforms[channel]
        ]
        if not voltages:
            return
        ymin = min(voltages)
        ymax = max(voltages)
        padding = max((ymax - ymin) * 0.08, 0.05)
        self.setYRange(ymin - padding, ymax + padding)

    def auto_xy_range(self) -> None:
        """Fit both axes to all waveform content."""

        self.autoRange()

    def _begin_drag_point(self, _channel: str, _index: int) -> None:
        self._drag_project = self.project.clone()
        self._drag_changed = False

    def _preview_drag_point(self, channel: str, index: int, time_value: float, voltage: float) -> None:
        if self._drag_project is None:
            self._drag_project = self.project.clone()
        next_project = self._drag_project.clone()
        if index >= len(next_project.waveforms[channel]):
            return
        time_value, voltage = self._snap(time_value, voltage)
        next_project.waveforms[channel][index] = WaveformPoint(time_value, voltage)
        # Do not sort during drag; stable point identity makes editing feel much
        # smoother. The final committed project is sorted in _finish_drag_point.
        self.project = next_project
        self._drag_changed = True
        self.refresh()
        self._show_drag_info(channel, time_value, voltage)
        self.cursorChanged.emit(time_value, voltage)

    def _finish_drag_point(self) -> None:
        if not self._drag_changed:
            self._drag_project = None
            return
        next_project = self.project.clone()
        next_project.enforce_monotonic_waveforms(self._minimum_time_step())
        self._drag_project = None
        self._drag_changed = False
        self.drag_info.hide()
        self.projectChanged.emit(next_project)

    def _add_point(self, channel: str, time_value: float, voltage: float) -> None:
        next_project = self.project.clone()
        time_value, voltage = self._snap(time_value, voltage)
        next_project.waveforms[channel].append(WaveformPoint(time_value, voltage))
        next_project.enforce_monotonic_waveforms(self._minimum_time_step())
        self.selected_point = self._find_point_after_repair(next_project, channel, time_value, voltage)
        self.projectChanged.emit(next_project)

    def _minimum_time_step(self) -> float:
        settings = self.project.settings
        return max(settings.minimum_point_spacing, 1e-12)

    def _find_point_after_repair(
        self, project: Project, channel: str, time_value: float, voltage: float
    ) -> tuple[str, int] | None:
        points = project.waveforms[channel]
        if not points:
            return None
        index = min(
            range(len(points)),
            key=lambda i: abs(points[i].time - time_value) + abs(points[i].voltage - voltage) * 1e-9,
        )
        return channel, index

    def _select_point(self, channel: str, index: int) -> None:
        if 0 <= index < len(self.project.waveforms[channel]):
            self.selected_point = (channel, index)
            self._update_selected_marker()
            point = self.project.waveforms[channel][index]
            self._show_drag_info(channel, point.time, point.voltage)

    def _select_nearest(self, channel: str, time_value: float) -> None:
        points = self.project.waveforms[channel]
        if not points:
            return
        index = min(range(len(points)), key=lambda i: abs(points[i].time - time_value))
        self._select_point(channel, index)

    def _update_selected_marker(self) -> None:
        if self.selected_point is None:
            self.selected_marker.setData([], [])
            return
        channel, index = self.selected_point
        points = self.project.waveforms[channel]
        if index >= len(points):
            self.selected_point = None
            self.selected_marker.setData([], [])
            return
        point = points[index]
        self.selected_marker.setData([point.time], [point.voltage])

    def _delete_point(self, channel: str, index: int) -> None:
        next_project = self.project.clone()
        if 0 <= index < len(next_project.waveforms[channel]):
            next_project.waveforms[channel].pop(index)
            if self.selected_point == (channel, index):
                self.selected_point = None
            self.projectChanged.emit(next_project)

    def _delete_nearest(self, channel: str, time_value: float) -> None:
        points = self.project.waveforms[channel]
        if not points:
            return
        index = min(range(len(points)), key=lambda i: abs(points[i].time - time_value))
        self._delete_point(channel, index)

    def _insert_sharp_edge(self, channel: str, time_value: float, rising: bool) -> None:
        points = self.project.waveforms[channel]
        low, high = self._edge_voltage_pair(channel)
        before_v, after_v = (low, high) if rising else (high, low)
        if points:
            nearest = min(points, key=lambda point: abs(point.time - time_value))
            center_time = nearest.time if abs(nearest.time - time_value) < self._minimum_time_step() * 4 else time_value
        else:
            center_time = time_value
        center_time, _ = self._snap(center_time, before_v)
        spacing = self._minimum_time_step()
        first_time = max(0.0, center_time)
        second_time = first_time + spacing
        next_project = self.project.clone()
        next_project.waveforms[channel].extend(
            [WaveformPoint(first_time, before_v), WaveformPoint(second_time, after_v)]
        )
        next_project.enforce_monotonic_waveforms(spacing)
        self.selected_point = self._find_point_after_repair(next_project, channel, second_time, after_v)
        self.projectChanged.emit(next_project)

    def _handle_segment_click(self, time_value: float, voltage: float) -> bool:
        segment = self._nearest_segment(self.active_channel, time_value, voltage)
        if segment is None:
            return False
        channel, left_index, right_index = segment
        points = self.project.waveforms[channel]
        left = points[left_index]
        right = points[right_index]
        spacing = self._minimum_time_step()
        if abs(right.time - left.time) <= spacing * 4:
            next_project = self.project.clone()
            next_project.waveforms[channel][left_index] = WaveformPoint(left.time, right.voltage)
            next_project.waveforms[channel][right_index] = WaveformPoint(right.time, left.voltage)
            self.selected_point = (channel, right_index)
            self.projectChanged.emit(next_project)
            return True
        rising = voltage >= (left.voltage + right.voltage) / 2.0
        self._insert_sharp_edge(channel, time_value, rising=rising)
        return True

    def _nearest_segment(self, channel: str, time_value: float, voltage: float) -> tuple[str, int, int] | None:
        points = self.project.waveforms[channel]
        if len(points) < 2:
            return None
        best: tuple[float, int, int] | None = None
        view_box = self.getPlotItem().vb
        click_scene = view_box.mapViewToScene(pg.Point(time_value, voltage))
        for index in range(len(points) - 1):
            left = points[index]
            right = points[index + 1]
            if not (min(left.time, right.time) <= time_value <= max(left.time, right.time)):
                continue
            left_scene = view_box.mapViewToScene(pg.Point(left.time, left.voltage))
            right_scene = view_box.mapViewToScene(pg.Point(right.time, right.voltage))
            distance = self._point_to_segment_distance_px(click_scene, left_scene, right_scene)
            if best is None or distance < best[0]:
                best = (distance, index, index + 1)
        if best is None or best[0] > 10.0:
            return None
        return channel, best[1], best[2]

    def _point_to_segment_distance_px(self, point, left, right) -> float:
        px, py = point.x(), point.y()
        x1, y1 = left.x(), left.y()
        x2, y2 = right.x(), right.y()
        dx = x2 - x1
        dy = y2 - y1
        if dx == 0 and dy == 0:
            return float(np.hypot(px - x1, py - y1))
        t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
        nearest_x = x1 + t * dx
        nearest_y = y1 + t * dy
        return float(np.hypot(px - nearest_x, py - nearest_y))

    def _edge_voltage_pair(self, channel: str) -> tuple[float, float]:
        points = self.project.waveforms[channel]
        if not points:
            return 0.0, 1.0
        values = [point.voltage for point in points]
        low = min(values)
        high = max(values)
        if low == high:
            high = low + 1.0
        return low, high

    def _draw_measurement_overlays(self) -> None:
        for item in self.measurement_items:
            self.removeItem(item)
        self.measurement_items = []
        for event in self.project.measurements:
            line = pg.InfiniteLine(
                pos=event.tm,
                angle=90,
                movable=False,
                pen=pg.mkPen("#ffd166", width=1.2, style=Qt.DotLine),
            )
            self.addItem(line)
            self.measurement_items.append(line)

    def _update_sample_info(self) -> None:
        lines = []
        for channel in CHANNELS:
            points = self.project.waveforms[channel]
            if len(points) < 2:
                lines.append(f"{channel.upper()}: dt --")
                continue
            times = np.array([point.time for point in points], dtype=float)
            diffs = np.diff(np.sort(times))
            positive = diffs[diffs > 0]
            if len(positive) == 0:
                lines.append(f"{channel.upper()}: dt duplicate")
                continue
            lines.append(
                f"{channel.upper()}: min dt {format_si(float(np.min(positive)), 's')}, "
                f"med dt {format_si(float(np.median(positive)), 's')}"
            )
        self.sample_info.setText("\n".join(lines))
        self._position_overlay_text()

    def _position_overlay_text(self) -> None:
        view_range = self.getViewBox().viewRange()
        x_min, x_max = view_range[0]
        y_min, y_max = view_range[1]
        self.sample_info.setPos(
            x_min + (x_max - x_min) * 0.015,
            y_max - (y_max - y_min) * 0.04,
        )
        self.cursor_info.setPos(
            x_max - (x_max - x_min) * 0.015,
            y_max - (y_max - y_min) * 0.04,
        )

    def _show_drag_info(self, channel: str, time_value: float, voltage: float) -> None:
        self.drag_info.setText(
            f"{channel.upper()}  t={format_si(time_value, 's')}  V={voltage:.6g}"
        )
        self.drag_info.setPos(time_value, voltage)
        self.drag_info.show()

    def _mouse_moved(self, scene_pos) -> None:
        if self.sceneBoundingRect().contains(scene_pos):
            point = self.getPlotItem().vb.mapSceneToView(scene_pos)
            self.cursor_line.setValue(point.x())
            snap_text = ""
            if self.project.settings.snap_enabled:
                snap_text = (
                    f"\nSnap: {format_si(self._active_snap_time(), 's')}, "
                    f"{self._active_snap_voltage():.6g} V"
                )
            self.cursor_info.setText(
                f"t={format_si(float(point.x()), 's')}\nV={float(point.y()):.6g}{snap_text}"
            )
            self.cursorChanged.emit(float(point.x()), float(point.y()))
