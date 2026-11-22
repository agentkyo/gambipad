"""Windows backends: ViGEmBus virtual pads and SendInput keyboard/mouse."""
from __future__ import annotations

import ctypes
from ctypes import wintypes

from ..keys import KEYS, MEDIA
from ..state import PadState
from . import KeyMouse, RumbleCallback

VIGEM_URL = "https://github.com/nefarius/ViGEmBus/releases/latest"

_XBOX = {
    "cross": "XUSB_GAMEPAD_A",
    "circle": "XUSB_GAMEPAD_B",
    "square": "XUSB_GAMEPAD_X",
    "triangle": "XUSB_GAMEPAD_Y",
    "l1": "XUSB_GAMEPAD_LEFT_SHOULDER",
    "r1": "XUSB_GAMEPAD_RIGHT_SHOULDER",
    "share": "XUSB_GAMEPAD_BACK",
    "touchpad": "XUSB_GAMEPAD_BACK",
    "options": "XUSB_GAMEPAD_START",
    "ps": "XUSB_GAMEPAD_GUIDE",
    "l3": "XUSB_GAMEPAD_LEFT_THUMB",
    "r3": "XUSB_GAMEPAD_RIGHT_THUMB",
    "up": "XUSB_GAMEPAD_DPAD_UP",
    "down": "XUSB_GAMEPAD_DPAD_DOWN",
    "left": "XUSB_GAMEPAD_DPAD_LEFT",
    "right": "XUSB_GAMEPAD_DPAD_RIGHT",
}
_DS4 = {
    "cross": "DS4_BUTTON_CROSS",
    "circle": "DS4_BUTTON_CIRCLE",
    "square": "DS4_BUTTON_SQUARE",
    "triangle": "DS4_BUTTON_TRIANGLE",
    "l1": "DS4_BUTTON_SHOULDER_LEFT",
    "r1": "DS4_BUTTON_SHOULDER_RIGHT",
    "l2": "DS4_BUTTON_TRIGGER_LEFT",
    "r2": "DS4_BUTTON_TRIGGER_RIGHT",
    "share": "DS4_BUTTON_SHARE",
    "options": "DS4_BUTTON_OPTIONS",
    "l3": "DS4_BUTTON_THUMB_LEFT",
    "r3": "DS4_BUTTON_THUMB_RIGHT",
}
_DS4_DPAD = {
    (0, -1): "NORTH",
    (1, -1): "NORTHEAST",
    (1, 0): "EAST",
    (1, 1): "SOUTHEAST",
    (0, 1): "SOUTH",
    (-1, 1): "SOUTHWEST",
    (-1, 0): "WEST",
    (-1, -1): "NORTHWEST",
    (0, 0): "NONE",
}


def _u8(value: float) -> int:
    return max(0, min(255, int(round(128 + value * 127))))


def _i16(value: float) -> int:
    return max(-32768, min(32767, int(round(value * 32767))))


class VigemPad:
    def __init__(self, kind: str, on_rumble: RumbleCallback):
        try:
            import vgamepad as vg
        except Exception as error:  # the DLL load fails when ViGEmBus is missing
            raise RuntimeError(f"ViGEmBus is not available ({error}). Install it from {VIGEM_URL}") from error
        self._vg = vg
        self.kind = "ds4" if kind == "ds4" else "xbox360"
        try:
            self.pad = vg.VDS4Gamepad() if self.kind == "ds4" else vg.VX360Gamepad()
        except Exception as error:
            raise RuntimeError(f"Could not create the virtual controller ({error}). Install ViGEmBus from {VIGEM_URL}") from error
        self._last = None

        def notify(client, target, large_motor, small_motor, led_number, user_data):
            on_rumble(small_motor, large_motor)

        self._notify = notify
        self.pad.register_notification(notify)

    def apply(self, pad: PadState) -> None:
        if self.kind == "ds4":
            self._apply_ds4(pad)
            return
        key = (pad.buttons, pad.lx, pad.ly, pad.rx, pad.ry, pad.l2, pad.r2)
        if key == self._last:
            return
        self._last = key
        vg, target = self._vg, self.pad
        target.reset()
        for name in pad.buttons:
            code = _XBOX.get(name)
            if code:
                target.press_button(vg.XUSB_BUTTON[code])
        target.left_trigger(int(round(pad.l2 * 255)))
        target.right_trigger(int(round(pad.r2 * 255)))
        # XInput has Y growing upwards.
        target.left_joystick(_i16(pad.lx), _i16(-pad.ly))
        target.right_joystick(_i16(pad.rx), _i16(-pad.ry))
        target.update()

    def _apply_ds4(self, pad: PadState) -> None:
        vg, target = self._vg, self.pad
        target.reset()
        for name in pad.buttons:
            code = _DS4.get(name)
            if code:
                target.press_button(vg.DS4_BUTTONS[code])
        if "ps" in pad.buttons:
            target.press_special_button(vg.DS4_SPECIAL_BUTTONS.DS4_SPECIAL_BUTTON_PS)
        if "touchpad" in pad.buttons:
            target.press_special_button(vg.DS4_SPECIAL_BUTTONS.DS4_SPECIAL_BUTTON_TOUCHPAD)
        dx = ("right" in pad.buttons) - ("left" in pad.buttons)
        dy = ("down" in pad.buttons) - ("up" in pad.buttons)
        target.directional_pad(vg.DS4_DPAD_DIRECTIONS["DS4_BUTTON_DPAD_" + _DS4_DPAD[(dx, dy)]])
        target.left_trigger(int(round(pad.l2 * 255)))
        target.right_trigger(int(round(pad.r2 * 255)))
        target.left_joystick(_u8(pad.lx), _u8(pad.ly))
        target.right_joystick(_u8(pad.rx), _u8(pad.ry))
        fingers = [(t.x, min(t.y, 941)) for t in pad.touches[:2]] + [None, None]
        target.touchpad(fingers[0], fingers[1])
        target.gyroscope(*pad.gyro)
        target.accelerometer(*pad.accel)
        target.update()

    def close(self) -> None:
        try:
            self.pad.reset()
            self.pad.update()
            self.pad.unregister_notification()
        except Exception:
            pass
        self.pad = None  # the ViGEm target is unplugged when the object is collected


# ------------------------------------------------------------ keyboard/mouse

INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP, KEYEVENTF_SCANCODE = 0x1, 0x2, 0x8
MOUSEEVENTF_MOVE, MOUSEEVENTF_WHEEL = 0x0001, 0x0800
_MOUSE_FLAGS = {"left": (0x0002, 0x0004), "right": (0x0008, 0x0010), "middle": (0x0020, 0x0040)}
ULONG_PTR = ctypes.c_size_t


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class _UNION(ctypes.Union):
    _fields_ = [("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _UNION)]


class WindowsKeyMouse(KeyMouse):
    def __init__(self):
        super().__init__()
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(_INPUT), ctypes.c_int)
        self._user32.SendInput.restype = wintypes.UINT

    def _send(self, item: _INPUT) -> None:
        self._user32.SendInput(1, ctypes.byref(item), ctypes.sizeof(_INPUT))

    def _key(self, name: str, down: bool) -> None:
        if name not in KEYS:
            return
        vk, _, extended = KEYS[name]
        flags = 0 if down else KEYEVENTF_KEYUP
        if extended:
            flags |= KEYEVENTF_EXTENDEDKEY
        scan = 0 if name in MEDIA else self._user32.MapVirtualKeyW(vk, 0)
        item = _INPUT(type=INPUT_KEYBOARD)
        if scan:  # games read scan codes, not virtual keys
            item.u.ki = _KEYBDINPUT(0, scan, flags | KEYEVENTF_SCANCODE, 0, 0)
        else:
            item.u.ki = _KEYBDINPUT(vk, 0, flags, 0, 0)
        self._send(item)

    def _mouse(self, flags: int, dx: int = 0, dy: int = 0, data: int = 0) -> None:
        item = _INPUT(type=INPUT_MOUSE)
        item.u.mi = _MOUSEINPUT(dx, dy, data & 0xFFFFFFFF, flags, 0, 0)
        self._send(item)

    def _button(self, name: str, down: bool) -> None:
        if name in _MOUSE_FLAGS:
            self._mouse(_MOUSE_FLAGS[name][0 if down else 1])

    def _move(self, dx: int, dy: int) -> None:
        self._mouse(MOUSEEVENTF_MOVE, dx, dy)

    def _wheel(self, ticks: int) -> None:
        self._mouse(MOUSEEVENTF_WHEEL, data=ticks * 120)
