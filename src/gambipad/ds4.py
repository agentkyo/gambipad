"""DualShock 4 wire protocol: input report parsing and output report building.

Works for the original pads and for the many clones that copy Sony's USB IDs.
Everything here is pure (bytes in, values out) so it is covered by unit tests
and never needs a controller plugged in.
"""
from __future__ import annotations

import struct
import zlib

from .state import PadState, Touch

#: (vendor id, product id) -> human name. Clones almost always reuse these.
KNOWN_DEVICES: dict[tuple[int, int], str] = {
    (0x054C, 0x05C4): "DualShock 4 (CUH-ZCT1)",
    (0x054C, 0x09CC): "DualShock 4 (CUH-ZCT2)",
    (0x054C, 0x0BA0): "DualShock 4 USB wireless adaptor",
}

USB_INPUT_ID = 0x01
BT_INPUT_ID = 0x11
USB_OUTPUT_ID = 0x05
BT_OUTPUT_ID = 0x11

_HAT = {
    0: ("up",),
    1: ("up", "right"),
    2: ("right",),
    3: ("down", "right"),
    4: ("down",),
    5: ("down", "left"),
    6: ("left",),
    7: ("up", "left"),
}
_FACE_BITS = ((0x10, "square"), (0x20, "cross"), (0x40, "circle"), (0x80, "triangle"))
_MISC_BITS = (
    (0x01, "l1"),
    (0x02, "r1"),
    (0x04, "l2"),
    (0x08, "r2"),
    (0x10, "share"),
    (0x20, "options"),
    (0x40, "l3"),
    (0x80, "r3"),
)


def _axis(value: int) -> float:
    return max(-1.0, min(1.0, (value - 128) / 127.0))


def _touch(chunk: bytes) -> Touch | None:
    if chunk[0] & 0x80:  # bit 7 set = finger lifted
        return None
    x = chunk[1] | ((chunk[2] & 0x0F) << 8)
    y = (chunk[2] >> 4) | (chunk[3] << 4)
    return Touch(chunk[0] & 0x7F, x, y)


def parse_report(data: bytes) -> PadState | None:
    """Decode one HID input report. Returns None for reports we do not know."""
    if not data:
        return None
    if data[0] == USB_INPUT_ID:
        o = 1
    elif data[0] == BT_INPUT_ID:
        o = 3
    else:
        return None
    if len(data) < o + 9:
        return None

    b1, b2, b3 = data[o + 4], data[o + 5], data[o + 6]
    buttons = set(_HAT.get(b1 & 0x0F, ()))
    buttons.update(name for mask, name in _FACE_BITS if b1 & mask)
    buttons.update(name for mask, name in _MISC_BITS if b2 & mask)
    if b3 & 0x01:
        buttons.add("ps")
    if b3 & 0x02:
        buttons.add("touchpad")

    gyro = accel = (0, 0, 0)
    battery = None
    charging = False
    touches: list[Touch] = []
    if len(data) >= o + 30:
        gyro = struct.unpack_from("<3h", data, o + 12)
        accel = struct.unpack_from("<3h", data, o + 18)
        raw = data[o + 29]
        charging = bool(raw & 0x10)
        level = raw & 0x0F
        # On cable the pad reports 0..11 (11 = full), on battery 0..8.
        battery = min(100, round(level * 100 / (11 if charging else 8)))
    if len(data) >= o + 42 and data[o + 32] > 0:
        for start in (o + 34, o + 38):
            touch = _touch(data[start : start + 4])
            if touch:
                touches.append(touch)

    return PadState(
        buttons=frozenset(buttons),
        lx=_axis(data[o]),
        ly=_axis(data[o + 1]),
        rx=_axis(data[o + 2]),
        ry=_axis(data[o + 3]),
        l2=data[o + 7] / 255.0,
        r2=data[o + 8] / 255.0,
        touches=tuple(touches),
        gyro=gyro,
        accel=accel,
        battery=battery,
        charging=charging,
    )


def is_smeared(data: bytes) -> bool:
    """True when a USB report shows the "every fourth byte is a copy" defect.

    Seen on a 054C:09CC clone: in every report, byte 4k+3 repeats byte 4k+2.
    That overwrites the right stick X axis (with left stick Y), the PS and
    touchpad-click bits (with L1 and R1), the high byte of the timestamp and
    the touch data. One report can match by chance on a healthy pad, so callers
    must require a long unbroken run - the timestamp alone breaks it at once.
    """
    if len(data) < 44 or data[0] != USB_INPUT_ID:
        return False
    return all(data[i] == data[i + 1] for i in range(2, 44, 4))


def desmear(state: PadState) -> PadState:
    """Remove what a smeared report cannot be trusted for."""
    return state.with_(buttons=state.buttons - {"ps", "touchpad"}, rx=0.0, touches=())


def _byte(value: float) -> int:
    return max(0, min(255, int(round(value))))


def build_output(
    weak: int = 0,
    strong: int = 0,
    rgb: tuple[int, int, int] = (0, 0, 0),
    flash: tuple[int, int] = (0, 0),
    bluetooth: bool = False,
) -> bytes:
    """Build the rumble + light bar output report.

    ``weak`` is the small (right, high frequency) motor, ``strong`` the big
    (left, low frequency) one, both 0..255. ``flash`` is (on, off) in units of
    10 ms; (0, 0) keeps the light solid.
    """
    payload = bytes(
        [
            _byte(weak),
            _byte(strong),
            _byte(rgb[0]),
            _byte(rgb[1]),
            _byte(rgb[2]),
            _byte(flash[0]),
            _byte(flash[1]),
        ]
    )
    if not bluetooth:
        buf = bytearray(32)
        buf[0] = USB_OUTPUT_ID
        buf[1] = 0x07  # rumble | light bar | flash are valid
        buf[2] = 0x04
        buf[4:11] = payload
        return bytes(buf)

    buf = bytearray(78)
    buf[0] = BT_OUTPUT_ID
    buf[1] = 0xC0  # HID data + CRC present
    buf[3] = 0x07
    buf[6:13] = payload
    crc = zlib.crc32(b"\xa2" + bytes(buf[:74]))
    struct.pack_into("<I", buf, 74, crc)
    return bytes(buf)
