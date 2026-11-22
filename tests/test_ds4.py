import struct
import zlib

from gambipad import ds4


def usb_report(**over) -> bytearray:
    r = bytearray(64)
    r[0] = 0x01
    r[1:5] = bytes([128, 128, 128, 128])
    r[5] = 0x08  # hat released
    r[35] = 0x80  # no finger
    r[39] = 0x80
    for index, value in over.items():
        r[int(index[1:])] = value
    return r


def test_idle_report():
    state = ds4.parse_report(bytes(usb_report()))
    assert state.buttons == frozenset()
    assert (state.lx, state.ly, state.rx, state.ry) == (0, 0, 0, 0)
    assert state.touches == ()


def test_real_clone_capture():
    # Captured from a 054C:09CC clone at rest.
    raw = bytes.fromhex("01808080800800000000" + "3d3d00ebffffffeeffffffea1f1f0600000000000a0a000100006016262" + "6bac41d1d")
    state = ds4.parse_report(raw.ljust(64, b"\0"))
    assert state.buttons == frozenset()
    assert state.gyro == (-21, -1, -18)
    assert state.battery is not None


def test_buttons_and_hat():
    state = ds4.parse_report(bytes(usb_report(b5=0x20 | 0x01, b6=0x01 | 0x80, b7=0x03)))
    assert state.buttons == {"cross", "up", "right", "l1", "r3", "ps", "touchpad"}


def test_axes_and_triggers():
    state = ds4.parse_report(bytes(usb_report(b1=0, b2=255, b8=255, b9=51)))
    assert state.lx == -1.0 and state.ly == 1.0
    assert state.l2 == 1.0 and abs(state.r2 - 0.2) < 1e-6


def test_touch_decoding():
    r = usb_report(b33=1, b35=0x05)
    x, y = 1000, 500
    r[36] = x & 0xFF
    r[37] = ((x >> 8) & 0x0F) | ((y & 0x0F) << 4)
    r[38] = y >> 4
    state = ds4.parse_report(bytes(r))
    assert len(state.touches) == 1
    assert (state.touches[0].id, state.touches[0].x, state.touches[0].y) == (5, 1000, 500)


def test_battery_scales():
    assert ds4.parse_report(bytes(usb_report(b30=0x1B))).battery == 100
    assert ds4.parse_report(bytes(usb_report(b30=0x1B))).charging is True
    assert ds4.parse_report(bytes(usb_report(b30=0x04))).battery == 50


def test_bluetooth_report_offset():
    r = bytearray(78)
    r[0] = 0x11
    r[3:7] = bytes([128, 128, 128, 128])
    r[7] = 0x08 | 0x40  # circle
    state = ds4.parse_report(bytes(r))
    assert state.buttons == {"circle"}


def test_unknown_and_short_reports():
    assert ds4.parse_report(b"") is None
    assert ds4.parse_report(b"\x7f" + bytes(63)) is None
    assert ds4.parse_report(b"\x01\x80\x80") is None
    short = ds4.parse_report(bytes(usb_report())[:10])
    assert short is not None and short.battery is None


def test_usb_output_layout():
    out = ds4.build_output(weak=10, strong=200, rgb=(1, 2, 3), flash=(4, 5))
    assert len(out) == 32
    assert out[:3] == bytes([0x05, 0x07, 0x04])
    assert out[4:11] == bytes([10, 200, 1, 2, 3, 4, 5])


def test_output_clamps():
    out = ds4.build_output(weak=999, strong=-5, rgb=(300, 0, 0))
    assert out[4] == 255 and out[5] == 0 and out[6] == 255


def test_bluetooth_output_crc():
    out = ds4.build_output(weak=1, strong=2, rgb=(3, 4, 5), bluetooth=True)
    assert len(out) == 78 and out[0] == 0x11
    assert out[6:11] == bytes([1, 2, 3, 4, 5])
    assert struct.unpack_from("<I", out, 74)[0] == zlib.crc32(b"\xa2" + out[:74])
