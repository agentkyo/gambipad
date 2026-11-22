"""Keyboard vocabulary used by ``key:<name>`` targets, with per-platform codes."""
from __future__ import annotations

import string

#: name -> (Windows virtual key, Linux evdev key name, extended key on Windows)
_SPECIAL: dict[str, tuple[int, str, bool]] = {
    "space": (0x20, "KEY_SPACE", False),
    "enter": (0x0D, "KEY_ENTER", False),
    "esc": (0x1B, "KEY_ESC", False),
    "tab": (0x09, "KEY_TAB", False),
    "backspace": (0x08, "KEY_BACKSPACE", False),
    "delete": (0x2E, "KEY_DELETE", True),
    "insert": (0x2D, "KEY_INSERT", True),
    "home": (0x24, "KEY_HOME", True),
    "end": (0x23, "KEY_END", True),
    "pageup": (0x21, "KEY_PAGEUP", True),
    "pagedown": (0x22, "KEY_PAGEDOWN", True),
    "up": (0x26, "KEY_UP", True),
    "down": (0x28, "KEY_DOWN", True),
    "left": (0x25, "KEY_LEFT", True),
    "right": (0x27, "KEY_RIGHT", True),
    "shift": (0xA0, "KEY_LEFTSHIFT", False),
    "ctrl": (0xA2, "KEY_LEFTCTRL", False),
    "alt": (0xA4, "KEY_LEFTALT", False),
    "win": (0x5B, "KEY_LEFTMETA", True),
    "capslock": (0x14, "KEY_CAPSLOCK", False),
    "minus": (0xBD, "KEY_MINUS", False),
    "equal": (0xBB, "KEY_EQUAL", False),
    "comma": (0xBC, "KEY_COMMA", False),
    "period": (0xBE, "KEY_DOT", False),
    "slash": (0xBF, "KEY_SLASH", False),
    "semicolon": (0xBA, "KEY_SEMICOLON", False),
    "quote": (0xDE, "KEY_APOSTROPHE", False),
    "lbracket": (0xDB, "KEY_LEFTBRACE", False),
    "rbracket": (0xDD, "KEY_RIGHTBRACE", False),
    "backslash": (0xDC, "KEY_BACKSLASH", False),
    "grave": (0xC0, "KEY_GRAVE", False),
    "printscreen": (0x2C, "KEY_SYSRQ", True),
    "volume_up": (0xAF, "KEY_VOLUMEUP", True),
    "volume_down": (0xAE, "KEY_VOLUMEDOWN", True),
    "mute": (0xAD, "KEY_MUTE", True),
    "play_pause": (0xB3, "KEY_PLAYPAUSE", True),
    "next_track": (0xB0, "KEY_NEXTSONG", True),
    "prev_track": (0xB1, "KEY_PREVIOUSSONG", True),
}

#: Keys without a hardware scan code; sent as virtual keys on Windows.
MEDIA = ("volume_up", "volume_down", "mute", "play_pause", "next_track", "prev_track")

KEYS: dict[str, tuple[int, str, bool]] = {}
for _c in string.ascii_lowercase:
    KEYS[_c] = (ord(_c.upper()), f"KEY_{_c.upper()}", False)
for _d in string.digits:
    KEYS[_d] = (ord(_d), f"KEY_{_d}", False)
for _n in range(1, 13):
    KEYS[f"f{_n}"] = (0x6F + _n, f"KEY_F{_n}", False)
KEYS.update(_SPECIAL)

KEY_NAMES: tuple[str, ...] = tuple(KEYS)
