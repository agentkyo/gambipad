"""Linux backends built on uinput (python-evdev).

The virtual controller identifies itself as an Xbox 360 pad so SDL, Steam and
Proton map it without any configuration. Rumble requests from games arrive as
force feedback uploads and are forwarded to the real controller.

Needs write access to /dev/uinput - see packaging/linux/70-gambipad.rules.
"""
from __future__ import annotations

import select
import threading

from ..keys import KEYS
from ..state import PadState
from . import KeyMouse, RumbleCallback

_BUTTONS = {
    "cross": "BTN_A",
    "circle": "BTN_B",
    "square": "BTN_X",
    "triangle": "BTN_Y",
    "l1": "BTN_TL",
    "r1": "BTN_TR",
    "share": "BTN_SELECT",
    "touchpad": "BTN_SELECT",
    "options": "BTN_START",
    "ps": "BTN_MODE",
    "l3": "BTN_THUMBL",
    "r3": "BTN_THUMBR",
}


class UinputPad:
    kind = "xbox360"

    def __init__(self, kind: str, on_rumble: RumbleCallback):
        try:
            from evdev import AbsInfo, UInput, ecodes
        except ImportError as error:
            raise RuntimeError("python-evdev is not installed (pip install evdev)") from error
        self._e = ecodes
        self._on_rumble = on_rumble
        stick = AbsInfo(value=0, min=-32768, max=32767, fuzz=16, flat=128, resolution=0)
        trigger = AbsInfo(value=0, min=0, max=255, fuzz=0, flat=0, resolution=0)
        hat = AbsInfo(value=0, min=-1, max=1, fuzz=0, flat=0, resolution=0)
        capabilities = {
            ecodes.EV_KEY: sorted({getattr(ecodes, name) for name in _BUTTONS.values()}),
            ecodes.EV_ABS: [
                (ecodes.ABS_X, stick),
                (ecodes.ABS_Y, stick),
                (ecodes.ABS_RX, stick),
                (ecodes.ABS_RY, stick),
                (ecodes.ABS_Z, trigger),
                (ecodes.ABS_RZ, trigger),
                (ecodes.ABS_HAT0X, hat),
                (ecodes.ABS_HAT0Y, hat),
            ],
            ecodes.EV_FF: [ecodes.FF_RUMBLE],
        }
        try:
            self._ui = UInput(
                capabilities, name="GambiPad Virtual Controller", vendor=0x045E, product=0x028E, version=0x0110, max_effects=16
            )
        except Exception as error:
            raise RuntimeError(f"Cannot open /dev/uinput ({error}). Install the udev rule from packaging/linux.") from error
        self._last = None
        self._effects: dict[int, tuple[int, int]] = {}
        self._running = True
        self._thread = threading.Thread(target=self._feedback_loop, name="gambipad-ff", daemon=True)
        self._thread.start()

    def apply(self, pad: PadState) -> None:
        key = (pad.buttons, pad.lx, pad.ly, pad.rx, pad.ry, pad.l2, pad.r2)
        if key == self._last:
            return
        self._last = key
        e, ui = self._e, self._ui
        pressed = {_BUTTONS[name] for name in pad.buttons if name in _BUTTONS}
        for code in set(_BUTTONS.values()):
            ui.write(e.EV_KEY, getattr(e, code), int(code in pressed))
        for code, value in ((e.ABS_X, pad.lx), (e.ABS_Y, pad.ly), (e.ABS_RX, pad.rx), (e.ABS_RY, pad.ry)):
            ui.write(e.EV_ABS, code, max(-32768, min(32767, int(round(value * 32767)))))
        ui.write(e.EV_ABS, e.ABS_Z, int(round(pad.l2 * 255)))
        ui.write(e.EV_ABS, e.ABS_RZ, int(round(pad.r2 * 255)))
        ui.write(e.EV_ABS, e.ABS_HAT0X, ("right" in pad.buttons) - ("left" in pad.buttons))
        ui.write(e.EV_ABS, e.ABS_HAT0Y, ("down" in pad.buttons) - ("up" in pad.buttons))
        ui.syn()

    def _feedback_loop(self) -> None:
        e, ui = self._e, self._ui
        while self._running:
            try:
                ready, _, _ = select.select([ui.fd], [], [], 0.25)
                if not ready:
                    continue
                for event in ui.read():
                    if event.type == e.EV_UINPUT and event.code == e.UI_FF_UPLOAD:
                        upload = ui.begin_upload(event.value)
                        upload.retval = 0
                        rumble = upload.effect.u.ff_rumble_effect
                        self._effects[upload.effect.id] = (rumble.weak_magnitude >> 8, rumble.strong_magnitude >> 8)
                        ui.end_upload(upload)
                    elif event.type == e.EV_UINPUT and event.code == e.UI_FF_ERASE:
                        erase = ui.begin_erase(event.value)
                        erase.retval = 0
                        self._effects.pop(erase.effect_id, None)
                        ui.end_erase(erase)
                    elif event.type == e.EV_FF:
                        weak, strong = self._effects.get(event.code, (0, 0)) if event.value else (0, 0)
                        self._on_rumble(weak, strong)
            except OSError:
                return

    def close(self) -> None:
        self._running = False
        try:
            self._ui.close()
        except Exception:
            pass


class UinputKeyMouse(KeyMouse):
    def __init__(self):
        super().__init__()
        from evdev import UInput, ecodes

        self._e = ecodes
        self._codes = {name: getattr(ecodes, spec[1]) for name, spec in KEYS.items() if hasattr(ecodes, spec[1])}
        self._mouse = {"left": ecodes.BTN_LEFT, "right": ecodes.BTN_RIGHT, "middle": ecodes.BTN_MIDDLE}
        capabilities = {
            ecodes.EV_KEY: sorted(set(self._codes.values()) | set(self._mouse.values())),
            ecodes.EV_REL: [ecodes.REL_X, ecodes.REL_Y, ecodes.REL_WHEEL],
        }
        self._ui = UInput(capabilities, name="GambiPad Keyboard and Mouse")

    def _emit(self, kind: int, code: int, value: int) -> None:
        self._ui.write(kind, code, value)
        self._ui.syn()

    def _key(self, name: str, down: bool) -> None:
        if name in self._codes:
            self._emit(self._e.EV_KEY, self._codes[name], int(down))

    def _button(self, name: str, down: bool) -> None:
        if name in self._mouse:
            self._emit(self._e.EV_KEY, self._mouse[name], int(down))

    def _move(self, dx: int, dy: int) -> None:
        self._ui.write(self._e.EV_REL, self._e.REL_X, dx)
        self._ui.write(self._e.EV_REL, self._e.REL_Y, dy)
        self._ui.syn()

    def _wheel(self, ticks: int) -> None:
        self._emit(self._e.EV_REL, self._e.REL_WHEEL, ticks)

    def close(self) -> None:
        super().close()
        try:
            self._ui.close()
        except Exception:
            pass
