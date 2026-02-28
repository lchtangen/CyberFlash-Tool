"""tests/unit/test_new_widgets.py — Tests for the 8 new UI widgets.

Only tests pure-logic and data-oriented methods.  Paint/render paths that
require a fully initialised QPainter are exercised only at a smoke-test level
(instantiation + basic attribute setters).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QWidget
from pytestqt.qtbot import QtBot  # type: ignore[import]

from cyberflash.ui.widgets.command_palette import CommandPalette
from cyberflash.ui.widgets.device_timeline_widget import DeviceTimelineWidget
from cyberflash.ui.widgets.hex_viewer_widget import HexViewerWidget, _render_hex
from cyberflash.ui.widgets.inline_console import InlineConsole
from cyberflash.ui.widgets.split_view import SplitView
from cyberflash.ui.widgets.tachometer_gauge import TachometerGauge
from cyberflash.ui.widgets.toast_notification import _VARIANTS, ToastNotification
from cyberflash.ui.widgets.waveform_widget import WaveformWidget

# ---------------------------------------------------------------------------
# _render_hex (pure helper — no widget needed)
# ---------------------------------------------------------------------------


class TestRenderHex:
    def test_empty_bytes(self) -> None:
        assert _render_hex(b"") == ""

    def test_single_row(self) -> None:
        result = _render_hex(b"\x00\x01\x02\x03")
        assert "00000000" in result
        assert "00 01 02 03" in result

    def test_ascii_printable(self) -> None:
        result = _render_hex(b"Hello")
        assert "Hello" in result

    def test_non_printable_shown_as_dot(self) -> None:
        result = _render_hex(b"\x00\x01")
        assert ".." in result

    def test_multi_row(self) -> None:
        data = bytes(range(20))
        lines = _render_hex(data).strip().splitlines()
        assert len(lines) == 2  # 16 + 4

    def test_truncation_message(self) -> None:
        data = bytes(range(10))
        result = _render_hex(data, max_bytes=4)
        assert "truncated" in result

    def test_no_truncation_when_exact(self) -> None:
        data = bytes(range(4))
        result = _render_hex(data, max_bytes=4)
        assert "truncated" not in result


# ---------------------------------------------------------------------------
# HexViewerWidget
# ---------------------------------------------------------------------------


class TestHexViewerWidget:
    def test_initial_byte_count(self, qapp: object) -> None:
        w = HexViewerWidget()
        assert w.byte_count() == 0

    def test_load_bytes_updates_count(self, qapp: object) -> None:
        w = HexViewerWidget()
        w.load_bytes(b"ABC")
        assert w.byte_count() == 3

    def test_rendered_text_contains_hex(self, qapp: object) -> None:
        w = HexViewerWidget()
        w.load_bytes(b"\xff")
        assert "FF" in w.rendered_text()

    def test_clear_resets(self, qapp: object) -> None:
        w = HexViewerWidget()
        w.load_bytes(b"\x01\x02")
        w.clear()
        assert w.byte_count() == 0

    def test_load_file_missing_returns_false(self, qapp: object) -> None:
        w = HexViewerWidget()
        result = w.load_file(Path("/nonexistent/path/boot.img"))
        assert result is False

    def test_load_file_success(self, qapp: object, tmp_path: Path) -> None:
        p = tmp_path / "test.bin"
        p.write_bytes(b"\xde\xad\xbe\xef")
        w = HexViewerWidget()
        assert w.load_file(p) is True
        assert w.byte_count() == 4


# ---------------------------------------------------------------------------
# TachometerGauge
# ---------------------------------------------------------------------------


class TestTachometerGauge:
    def test_defaults(self, qapp: object) -> None:
        g = TachometerGauge()
        assert g.value() == 0.0
        assert g.maximum() == 100.0

    def test_set_value(self, qapp: object) -> None:
        g = TachometerGauge()
        g.set_value(73.5)
        assert g.value() == 73.5

    def test_value_clamped_to_max(self, qapp: object) -> None:
        g = TachometerGauge()
        g.set_value(200.0)
        assert g.value() == 100.0

    def test_value_clamped_to_zero(self, qapp: object) -> None:
        g = TachometerGauge()
        g.set_value(-10.0)
        assert g.value() == 0.0

    def test_set_max(self, qapp: object) -> None:
        g = TachometerGauge()
        g.set_max(200.0)
        assert g.maximum() == 200.0

    def test_set_label(self, qapp: object) -> None:
        g = TachometerGauge()
        g.set_label("CPU")
        assert g._label == "CPU"

    def test_zero_max_defaults_to_100(self, qapp: object) -> None:
        g = TachometerGauge(maximum=0.0)
        assert g.maximum() == 100.0

    def test_init_with_args(self, qapp: object) -> None:
        g = TachometerGauge(value=50.0, maximum=200.0, label="Mem")
        assert g.value() == 50.0
        assert g.maximum() == 200.0
        assert g._label == "Mem"


# ---------------------------------------------------------------------------
# WaveformWidget
# ---------------------------------------------------------------------------


class TestWaveformWidget:
    def test_initial_empty(self, qapp: object) -> None:
        w = WaveformWidget()
        assert w.sample_count() == 0

    def test_set_data(self, qapp: object) -> None:
        w = WaveformWidget()
        w.set_data([0.1, -0.5, 0.9])
        assert w.sample_count() == 3

    def test_values_clamped(self, qapp: object) -> None:
        w = WaveformWidget()
        w.set_data([5.0, -5.0])
        assert w._samples == [1.0, -1.0]

    def test_clear(self, qapp: object) -> None:
        w = WaveformWidget()
        w.set_data([0.1, 0.2])
        w.clear()
        assert w.sample_count() == 0

    def test_set_color_changes_color(self, qapp: object) -> None:
        from PySide6.QtGui import QColor
        w = WaveformWidget()
        w.set_color("#ff0000")
        assert w._color == QColor("#ff0000")


# ---------------------------------------------------------------------------
# DeviceTimelineWidget
# ---------------------------------------------------------------------------


class TestDeviceTimelineWidget:
    def test_initial_empty(self, qapp: object) -> None:
        t = DeviceTimelineWidget()
        assert t.event_count() == 0

    def test_add_event_increments_count(self, qapp: object) -> None:
        t = DeviceTimelineWidget()
        t.add_event("2025-01-01", "Flash started", "info")
        assert t.event_count() == 1

    def test_add_multiple_events(self, qapp: object) -> None:
        t = DeviceTimelineWidget()
        for i in range(5):
            t.add_event(f"T{i}", f"Event {i}", "success")
        assert t.event_count() == 5

    def test_clear_resets_count(self, qapp: object) -> None:
        t = DeviceTimelineWidget()
        t.add_event("T1", "evt", "info")
        t.clear()
        assert t.event_count() == 0

    def test_max_events_eviction(self, qapp: object) -> None:
        t = DeviceTimelineWidget(max_events=3)
        for i in range(5):
            t.add_event(f"T{i}", f"E{i}", "neutral")
        assert t.event_count() == 3

    def test_event_stored(self, qapp: object) -> None:
        t = DeviceTimelineWidget()
        t.add_event("2025-05-01 10:00", "boot complete", "success")
        assert t._events[0].label == "boot complete"
        assert t._events[0].event_type == "success"


# ---------------------------------------------------------------------------
# InlineConsole
# ---------------------------------------------------------------------------


class TestInlineConsole:
    def test_initial_empty_output(self, qapp: object) -> None:
        c = InlineConsole()
        assert c._output.toPlainText() == ""

    def test_append_line(self, qapp: object) -> None:
        c = InlineConsole()
        c.append_line("device online")
        assert "device online" in c._output.toPlainText()

    def test_clear_removes_text(self, qapp: object) -> None:
        c = InlineConsole()
        c.append_line("hello")
        c.clear()
        assert c._output.toPlainText() == ""

    def test_set_input_disabled_hides_bar(self, qapp: object) -> None:
        c = InlineConsole(show_input=True)
        c.set_input_enabled(False)
        assert c._input_bar.isHidden()

    def test_set_input_enabled_shows_bar(self, qapp: object) -> None:
        c = InlineConsole(show_input=False)
        assert c._input_bar.isHidden()
        c.set_input_enabled(True)
        assert not c._input_bar.isHidden()

    def test_command_entered_signal(self, qapp: object, qtbot: QtBot) -> None:
        c = InlineConsole()
        with qtbot.waitSignal(c.command_entered, timeout=1000) as blocker:
            c._prompt.setText("adb devices")
            c._on_submit()
        assert blocker.args == ["adb devices"]

    def test_empty_command_not_emitted(self, qapp: object) -> None:
        c = InlineConsole()
        signals_received: list[str] = []
        c.command_entered.connect(signals_received.append)
        c._prompt.setText("   ")
        c._on_submit()
        assert signals_received == []

    def test_set_placeholder(self, qapp: object) -> None:
        c = InlineConsole()
        c.set_placeholder("Enter shell command")
        assert c._prompt.placeholderText() == "Enter shell command"


# ---------------------------------------------------------------------------
# SplitView
# ---------------------------------------------------------------------------


class TestSplitView:
    def test_default_horizontal(self, qapp: object) -> None:
        s = SplitView()
        assert s.orientation() == Qt.Orientation.Horizontal

    def test_set_orientation_vertical(self, qapp: object) -> None:
        s = SplitView()
        s.set_orientation(Qt.Orientation.Vertical)
        assert s.orientation() == Qt.Orientation.Vertical

    def test_set_left_and_right(self, qapp: object) -> None:
        s = SplitView()
        left = QLabel("L")
        right = QLabel("R")
        s.set_left(left)
        s.set_right(right)
        assert s._left is left
        assert s._right is right

    def test_splitter_count_after_set(self, qapp: object) -> None:
        s = SplitView()
        s.set_left(QLabel("A"))
        s.set_right(QLabel("B"))
        assert s.splitter.count() == 2

    def test_sizes_len(self, qapp: object) -> None:
        s = SplitView()
        s.set_left(QLabel("L"))
        s.set_right(QLabel("R"))
        assert len(s.sizes()) == 2


# ---------------------------------------------------------------------------
# CommandPalette
# ---------------------------------------------------------------------------


class TestCommandPalette:
    def test_init(self, qapp: object) -> None:
        parent = QWidget()
        p = CommandPalette(parent)
        assert p._model is not None

    def test_show_palette_populates_model(self, qapp: object) -> None:
        parent = QWidget()
        p = CommandPalette(parent)
        cmds = ["Flash ROM", "Reboot Recovery", "Open Terminal"]
        p._model.setStringList(cmds)
        assert p._model.rowCount() == 3

    def test_command_selected_signal(self, qapp: object, qtbot: QtBot) -> None:
        parent = QWidget()
        p = CommandPalette(parent)
        p._model.setStringList(["Flash ROM", "Backup"])
        with qtbot.waitSignal(p.command_selected, timeout=1000) as blocker:
            idx = p._proxy.index(0, 0)
            p._on_activated(idx)
        assert blocker.args == ["Flash ROM"]


# ---------------------------------------------------------------------------
# ToastNotification
# ---------------------------------------------------------------------------


class TestToastNotification:
    def test_variant_keys_present(self) -> None:
        for key in ("success", "warning", "error", "info", "neutral"):
            assert key in _VARIANTS

    def test_creation(self, qapp: object) -> None:
        parent = QWidget()
        parent.resize(800, 600)
        toast = ToastNotification(parent, "Hello", variant="success")
        assert toast.text() == "Hello"

    def test_factory_classmethod(self, qapp: object) -> None:
        parent = QWidget()
        parent.resize(800, 600)
        toast = ToastNotification.show_toast(parent, "Done!", variant="info")
        assert isinstance(toast, ToastNotification)
        assert toast.text() == "Done!"

    def test_unknown_variant_uses_neutral(self, qapp: object) -> None:
        parent = QWidget()
        parent.resize(800, 600)
        # should not raise
        toast = ToastNotification(parent, "X", variant="banana")
        assert isinstance(toast, ToastNotification)
