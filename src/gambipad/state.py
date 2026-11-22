"""Controller state shared by every layer.

One vocabulary is used everywhere (PlayStation names). Output backends translate
it to whatever the virtual device speaks (Xbox names, evdev codes, ...).

Stick axes are floats in -1..1 with the raw HID orientation: X grows to the
right, Y grows *downwards*. Triggers are floats in 0..1.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

FACE = ("cross", "circle", "square", "triangle")
SHOULDER = ("l1", "r1", "l2", "r2")
SYSTEM = ("share", "options", "ps", "touchpad")
STICK_CLICK = ("l3", "r3")
DPAD = ("up", "down", "left", "right")

#: Every physical button a DualShock 4 style pad reports.
BUTTONS: tuple[str, ...] = FACE + SHOULDER + SYSTEM + STICK_CLICK + DPAD

#: Pseudo buttons produced by the touchpad in "buttons" mode.
TOUCH_BUTTONS: tuple[str, ...] = ("touch_left", "touch_right")

TOUCH_WIDTH = 1920
TOUCH_HEIGHT = 943


@dataclass(frozen=True)
class Touch:
    """One finger on the touchpad. ``x`` is 0..1919, ``y`` is 0..942."""

    id: int
    x: int
    y: int


@dataclass(frozen=True)
class PadState:
    buttons: frozenset[str] = frozenset()
    lx: float = 0.0
    ly: float = 0.0
    rx: float = 0.0
    ry: float = 0.0
    l2: float = 0.0
    r2: float = 0.0
    touches: tuple[Touch, ...] = ()
    gyro: tuple[int, int, int] = (0, 0, 0)
    accel: tuple[int, int, int] = (0, 0, 0)
    #: 0..100, or None when the report does not carry it.
    battery: int | None = None
    charging: bool = False

    def with_(self, **changes) -> "PadState":
        return replace(self, **changes)

    def pressed(self, name: str) -> bool:
        return name in self.buttons


@dataclass
class Frame:
    """What the engine wants the outside world to look like right now."""

    pad: PadState = field(default_factory=PadState)
    keys: frozenset[str] = frozenset()
    mouse_buttons: frozenset[str] = frozenset()
    mouse_dx: float = 0.0
    mouse_dy: float = 0.0
    wheel: int = 0
