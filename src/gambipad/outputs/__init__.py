"""Output backends: the virtual controller plus keyboard and mouse injection."""
from __future__ import annotations

import sys
from typing import Callable

from ..state import Frame, PadState

RumbleCallback = Callable[[int, int], None]  # (weak, strong), 0..255


class NullPad:
    """Used when the profile asks for no virtual controller, or none is available."""

    kind = "none"

    def apply(self, pad: PadState) -> None:
        pass

    def close(self) -> None:
        pass


class KeyMouse:
    """Turns frames into key/mouse events by diffing against the last frame."""

    def __init__(self):
        self._keys: frozenset[str] = frozenset()
        self._buttons: frozenset[str] = frozenset()
        self._fx = 0.0
        self._fy = 0.0

    def apply(self, frame: Frame) -> None:
        for name in frame.keys - self._keys:
            self._key(name, True)
        for name in self._keys - frame.keys:
            self._key(name, False)
        self._keys = frame.keys
        for name in frame.mouse_buttons - self._buttons:
            self._button(name, True)
        for name in self._buttons - frame.mouse_buttons:
            self._button(name, False)
        self._buttons = frame.mouse_buttons
        # Keep the fraction so slow finger movement is not rounded away.
        self._fx += frame.mouse_dx
        self._fy += frame.mouse_dy
        dx, dy = int(self._fx), int(self._fy)
        if dx or dy:
            self._fx -= dx
            self._fy -= dy
            self._move(dx, dy)
        if frame.wheel:
            self._wheel(frame.wheel)

    def release_all(self) -> None:
        self.apply(Frame())

    def close(self) -> None:
        self.release_all()

    def _key(self, name: str, down: bool) -> None: ...
    def _button(self, name: str, down: bool) -> None: ...
    def _move(self, dx: int, dy: int) -> None: ...
    def _wheel(self, ticks: int) -> None: ...


def create_pad(kind: str, on_rumble: RumbleCallback):
    """Create the virtual controller. Raises RuntimeError with a readable reason."""
    if kind == "none":
        return NullPad()
    if sys.platform == "win32":
        from .windows import VigemPad

        return VigemPad(kind, on_rumble)
    if sys.platform.startswith("linux"):
        from .linux import UinputPad

        return UinputPad(kind, on_rumble)
    raise RuntimeError(f"No virtual controller backend for {sys.platform}")


def create_keymouse() -> KeyMouse:
    try:
        if sys.platform == "win32":
            from .windows import WindowsKeyMouse

            return WindowsKeyMouse()
        if sys.platform.startswith("linux"):
            from .linux import UinputKeyMouse

            return UinputKeyMouse()
    except Exception:  # missing permissions or libraries: keep the pad working
        pass
    return KeyMouse()
