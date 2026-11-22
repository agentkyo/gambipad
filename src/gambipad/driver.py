"""The driver loop: read the real pad, run the engine, feed the outputs.

Runs in its own thread. The GUI and the CLI only talk to it through plain
attributes (latest states, status text) and a few thread-safe setters.
"""
from __future__ import annotations

import threading
import time
from typing import Callable

import hid

from . import ds4
from .engine import Engine, lightbar_color
from .hide import create_hider
from .outputs import NullPad, create_keymouse, create_pad
from .profile import normalize
from .state import Frame, PadState

READ_TIMEOUT_MS = 20
OUTPUT_REFRESH = 0.1  # resend light and rumble: clones forget a state that is sent only once
LIGHT_REFRESH = 0.05  # animation step for the light bar
SMEAR_REPORTS = 500  # unbroken run of corrupted reports before we call it a defect


def find_devices(extra=()) -> list[dict]:
    """Supported controllers currently plugged in, one entry per pad."""
    wanted = dict(ds4.KNOWN_DEVICES)
    for pair in extra or ():
        try:
            wanted[(int(pair[0]), int(pair[1]))] = "Custom device"
        except (TypeError, ValueError, IndexError):
            continue
    found: dict[bytes, dict] = {}
    for info in hid.enumerate():
        key = (info["vendor_id"], info["product_id"])
        if key not in wanted:
            continue
        # Windows lists one entry per HID collection; keep the gamepad one.
        if info.get("usage_page") not in (0, 1, None):
            continue
        # ViGEmBus virtual pads (ours included) carry a revision in their HID
        # path; real USB and Bluetooth pads do not. Never read a virtual pad.
        if b"&rev_" in bytes(info["path"]).lower():
            continue
        entry = dict(info)
        entry["model"] = wanted[key]
        found.setdefault(info["path"], entry)
    return list(found.values())


class Driver:
    def __init__(self, profile: dict | None = None, settings: dict | None = None, log: Callable[[str], None] = print):
        self.settings = settings or {}
        self.log = log
        self.engine = Engine(profile)
        self.status = "starting"
        self.device_name = ""
        self.bluetooth = False
        self.raw: PadState | None = None
        self.frame: Frame | None = None
        self.reports_per_second = 0
        self.output_note = ""
        self.hide_note = ""
        self.defect = ""  # "smear" when the pad corrupts its own reports
        self.capture: list | None = None

        self._pending: dict | None = None
        self._game_rumble = (0, 0)
        self._test_rumble: tuple[int, int, float] | None = None
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------- public api

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._running = True
        self._thread = threading.Thread(target=self._main, name="gambipad-driver", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None

    def set_profile(self, profile: dict) -> None:
        with self._lock:
            self._pending = normalize(profile)

    def test_rumble(self, weak: int, strong: int, seconds: float = 0.6) -> None:
        self._test_rumble = (weak, strong, time.monotonic() + seconds)

    def start_capture(self) -> None:
        self.capture = []

    def stop_capture(self) -> list:
        samples, self.capture = self.capture or [], None
        return samples

    # ------------------------------------------------------------------- loop

    def _main(self) -> None:
        while self._running:
            devices = find_devices(self.settings.get("extra_devices"))
            if not devices:
                self.status = "searching"
                self.raw = self.frame = None
                self._sleep(1.0)
                continue
            try:
                self._session(devices[0])
            except OSError as error:
                self.log(f"controller lost: {error}")
            except Exception as error:  # keep the thread alive, report, retry
                self.log(f"driver error: {error!r}")
                self.status = f"error: {error}"
            self._sleep(1.0)
        self.status = "stopped"

    def _sleep(self, seconds: float) -> None:
        end = time.monotonic() + seconds
        while self._running and time.monotonic() < end:
            time.sleep(0.05)

    def _make_pad(self, kind: str):
        try:
            pad = create_pad(kind, self._on_rumble)
            self.output_note = ""
            return pad
        except RuntimeError as error:
            self.output_note = str(error)
            self.log(self.output_note)
            return NullPad()

    def _on_rumble(self, weak: int, strong: int) -> None:
        self._game_rumble = (weak, strong)

    def _session(self, info: dict) -> None:
        device = hid.device()
        device.open_path(info["path"])
        self.device_name = f"{info.get('product_string') or 'Controller'} ({info['model']})"
        self.bluetooth = info.get("bus_type") == 2
        try:  # asks a Bluetooth pad to switch to full reports; harmless on USB
            device.get_feature_report(0x02, 64)
        except (OSError, ValueError):
            pass

        hider = create_hider()
        pad = NullPad()
        keymouse = create_keymouse()
        self._game_rumble = (0, 0)
        sent = None
        sent_at = 0.0
        count, count_from = 0, time.monotonic()
        smear_run = 0
        self.defect = ""
        try:
            kind = self.engine.profile["output"]
            pad = self._make_pad(kind)
            if self.settings.get("hide_physical", True) and not isinstance(pad, NullPad):
                self.hide_note = hider.hide(info["vendor_id"], info["product_id"])
            else:
                self.hide_note = "not hidden"
            self.status = "running"
            self.log(f"connected: {self.device_name} | virtual pad: {kind} | physical pad: {self.hide_note}")

            while self._running:
                data = bytes(device.read(78, READ_TIMEOUT_MS))
                with self._lock:
                    pending, self._pending = self._pending, None
                if pending is not None:
                    self.engine.set_profile(pending)
                    if pending["output"] != kind:
                        kind = pending["output"]
                        pad.close()
                        pad = self._make_pad(kind)
                    sent = None

                if data:
                    state = ds4.parse_report(data)
                    if state is not None:
                        if data[0] == ds4.BT_INPUT_ID:
                            self.bluetooth = True
                        if self.defect != "smear":
                            smear_run = smear_run + 1 if ds4.is_smeared(data) else 0
                            if smear_run >= SMEAR_REPORTS:
                                self.defect = "smear"
                                self.log(
                                    "defective controller: every fourth byte of its reports is a copy of the one before. "
                                    "Right stick X, PS, touchpad click and touch data never arrive and are ignored."
                                )
                        if self.defect == "smear":
                            state = ds4.desmear(state)
                        self.raw = state
                        count += 1
                        if self.capture is not None:
                            self.capture.append(state.buttons)

                now = time.monotonic()
                if now - count_from >= 1.0:
                    self.reports_per_second = int(count / (now - count_from))
                    count, count_from = 0, now
                    if self.reports_per_second == 0:
                        self.raw = None  # nothing arriving: do not hold stale input
                if self.raw is None:
                    continue

                frame = self.engine.process(self.raw)
                self.frame = frame
                pad.apply(frame.pad)
                keymouse.apply(frame)

                test = self._test_rumble
                if test and now < test[2]:
                    weak, strong = test[0], test[1]
                else:
                    self._test_rumble = None
                    weak, strong = self.engine.rumble(*self._game_rumble)
                rgb = lightbar_color(self.engine.profile["lightbar"], self.raw, now)
                wanted = (weak, strong, rgb)
                stale = now - sent_at > OUTPUT_REFRESH
                if (wanted != sent and now - sent_at > LIGHT_REFRESH) or (wanted[:2] != (sent or (0, 0, 0))[:2]) or stale:
                    device.write(ds4.build_output(weak, strong, rgb, bluetooth=self.bluetooth))
                    sent, sent_at = wanted, now
        finally:
            self.raw = self.frame = None
            for step in (
                lambda: device.write(ds4.build_output(0, 0, (0, 0, 0), bluetooth=self.bluetooth)),
                pad.close,
                keymouse.close,
                hider.restore,
                device.close,
            ):
                try:
                    step()
                except Exception:
                    pass
