"""Turn a Bluetooth controller off by dropping its Bluetooth link.

A DualShock 4 powers itself down as soon as the host disconnects it. Over USB
there is nothing to switch off: the cable keeps the pad alive.
"""
from __future__ import annotations

import re
import subprocess
import sys


def normalize_mac(serial: str | None) -> str:
    """'C4:F5:F8:51:6C:A1' or 'c4f5f8516ca1' -> 'c4f5f8516ca1'; '' when invalid."""
    mac = re.sub(r"[^0-9a-fA-F]", "", serial or "").lower()
    return mac if len(mac) == 12 else ""


def _windows_disconnect(mac: str) -> bool:
    import ctypes
    from ctypes import wintypes

    IOCTL_BTH_DISCONNECT_DEVICE = 0x41000C

    class FindRadioParams(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD)]

    bluetooth = ctypes.WinDLL("bthprops.cpl", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    bluetooth.BluetoothFindFirstRadio.restype = wintypes.HANDLE
    bluetooth.BluetoothFindFirstRadio.argtypes = (ctypes.POINTER(FindRadioParams), ctypes.POINTER(wintypes.HANDLE))
    bluetooth.BluetoothFindNextRadio.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.HANDLE))
    bluetooth.BluetoothFindRadioClose.argtypes = (wintypes.HANDLE,)
    kernel32.DeviceIoControl.argtypes = (
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.c_void_p,
    )
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)

    params = FindRadioParams(ctypes.sizeof(FindRadioParams))
    radio = wintypes.HANDLE()
    search = bluetooth.BluetoothFindFirstRadio(ctypes.byref(params), ctypes.byref(radio))
    if not search:
        return False
    address = ctypes.c_ulonglong(int(mac, 16))  # BTH_ADDR: the MAC in the low 48 bits
    done = False
    try:
        while True:
            returned = wintypes.DWORD()
            if kernel32.DeviceIoControl(
                radio, IOCTL_BTH_DISCONNECT_DEVICE, ctypes.byref(address), 8, None, 0, ctypes.byref(returned), None
            ):
                done = True
            kernel32.CloseHandle(radio)
            if done or not bluetooth.BluetoothFindNextRadio(search, ctypes.byref(radio)):
                break
    finally:
        bluetooth.BluetoothFindRadioClose(search)
    return done


def _linux_disconnect(mac: str) -> bool:
    address = ":".join(mac[i : i + 2] for i in range(0, 12, 2)).upper()
    try:
        done = subprocess.run(["bluetoothctl", "disconnect", address], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0


def power_off(serial: str | None) -> bool:
    """Disconnect the Bluetooth pad with this serial (its MAC). True when it worked."""
    mac = normalize_mac(serial)
    if not mac:
        return False
    try:
        if sys.platform == "win32":
            return _windows_disconnect(mac)
        if sys.platform.startswith("linux"):
            return _linux_disconnect(mac)
    except OSError:
        return False
    return False
