"""Smoke tests for the window: it builds, every page renders, edits reach the profile."""
import os
import re
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from gambipad import profile as profiles  # noqa: E402
from gambipad.gui import app as gui  # noqa: E402
from gambipad.gui import i18n  # noqa: E402
from gambipad.state import PadState, Touch  # noqa: E402


class FakeDriver:
    def __init__(self, profile, settings, log):
        self.status = "running"
        self.device_name = "Test pad"
        self.bluetooth = False
        self.raw = PadState(buttons=frozenset({"l1", "ps"}), lx=0.5, l2=0.7, touches=(Touch(1, 500, 300),), battery=80)
        self.frame = None
        self.reports_per_second = 250
        self.output_note = ""
        self.hide_note = "hidden"
        self.capture = None
        self.profile = profile

    def start(self): ...
    def stop(self): ...
    def test_rumble(self, *a): ...

    def set_profile(self, profile):
        self.profile = profile

    def start_capture(self):
        self.capture = [frozenset({"l1", "ps"})] * 10

    def stop_capture(self):
        samples, self.capture = self.capture, None
        return samples


@pytest.fixture
def window(tmp_path, monkeypatch):
    monkeypatch.setenv("GAMBIPAD_HOME", str(tmp_path))
    monkeypatch.setattr(gui, "Driver", FakeDriver)
    app = QApplication.instance() or QApplication([])
    win = gui.MainWindow()
    win.tray = None
    yield win
    win._quitting = True
    win._tick.stop()
    win._save_timer.stop()
    win.deleteLater()
    app.processEvents()


def test_window_builds_all_pages(window):
    assert window.tabs.count() == 6
    window._refresh()
    assert "Test pad" in window.status.text()
    assert window.pad_view.ghosted == frozenset()
    for index in range(window.tabs.count()):
        window.tabs.setCurrentIndex(index)
        window.grab()


def test_edit_reaches_driver_and_disk(window, tmp_path):
    window._set(("sticks", "left", "deadzone"), 0.25)
    assert window.driver.profile["sticks"]["left"]["deadzone"] == 0.25
    profiles.save_profile(window.profile)
    assert profiles.load_profile("Default")["sticks"]["left"]["deadzone"] == 0.25


def test_diagnose_flow_adds_fix(window):
    window.tabs.setCurrentIndex(5)
    window._diagnose_start()
    window._capture_end = 1.0  # already over
    window._diagnose_tick()
    assert window._found == [["l1", "ps"]]
    window._diagnose_apply()
    assert window.profile["ghosts"] == [["l1", "ps"]]
    window._refresh()
    assert window.pad_view.ghosted == {"ps"}


def test_macro_and_touch_mode_pages(window):
    window.profile["macros"]["combo"] = {"mode": "hold", "steps": [{"tap": "pad:cross", "ms": 50}, {"wait": 30}]}
    window.profile["buttons"]["triangle"] = {"type": "macro", "macro": "combo"}
    window.profile["touchpad"]["mode"] = "buttons"
    window.profile["combos"] = [{"buttons": ["l3", "r3"], "action": {"type": "button", "to": ["key:f5"]}, "suppress": True}]
    window._changed()
    window._reload()
    assert window.steps.count() == 2
    assert window.combo_list.count() == 1
    window._macro_delete()
    assert window.profile["buttons"]["triangle"] == {"type": "none"}


def test_every_ui_string_is_translated():
    source = "".join(p.read_text(encoding="utf-8") for p in Path(gui.__file__).parent.glob("*.py") if p.name != "i18n.py")
    used = set(re.findall(r'tr\(\s*"((?:[^"\\]|\\.)*)"\s*\)', source))
    labels = set(re.findall(r':\s*"([^"]+)",?\n', source.split("BUTTON_LABELS")[1].split("KINDS")[0]))
    plain = {s for s in used | labels if not re.fullmatch(r"[A-Z0-9 ]+", s)}
    missing = sorted(s for s in plain if s not in i18n.PT and s not in ("Share", "Options", "PS", "L1", "R1", "L2", "R2"))
    assert missing == []
