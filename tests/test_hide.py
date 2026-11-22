import json
import sys

import pytest

from gambipad import hide

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="HidHide is Windows only")

GAMING = json.dumps(
    [
        {
            "friendlyName": "pad",
            "devices": [
                {
                    "deviceInstancePath": "HID\\VID_054C&PID_09CC&MI_03\\b&1",
                    "baseContainerDeviceInstancePath": "USB\\VID_054C&PID_09CC\\9&2",
                },
                {"deviceInstancePath": "HID\\VID_1234&PID_0001\\x", "baseContainerDeviceInstancePath": "USB\\VID_1234&PID_0001\\y"},
            ],
        }
    ]
)


@pytest.fixture
def hider(tmp_path, monkeypatch):
    monkeypatch.setenv("GAMBIPAD_HOME", str(tmp_path))
    calls = []

    def fake_run(self, *args):
        calls.append(args)
        if args == ("--dev-gaming",):
            return GAMING
        if args[0] == "--cloak-state":
            return "--cloak-off\n"
        return ""

    monkeypatch.setattr(hide._WindowsHider, "_run", fake_run)
    monkeypatch.setattr(hide, "_hidhide_cli", lambda: tmp_path / "HidHideCLI.exe")
    return hide._WindowsHider(), calls, tmp_path


def test_hides_only_the_matching_pad_and_restores(hider):
    h, calls, home = hider
    assert h.hide(0x054C, 0x09CC) == "hidden"
    args = calls[-1]
    hidden = [args[i + 1] for i, a in enumerate(args) if a == "--dev-hide"]
    assert hidden == ["HID\\VID_054C&PID_09CC&MI_03\\b&1", "USB\\VID_054C&PID_09CC\\9&2"]
    assert "--app-reg" in args and args[-1] == "--cloak-on"
    assert (home / "hidhide-state.json").exists()

    h.restore()
    args = calls[-1]
    assert [args[i + 1] for i, a in enumerate(args) if a == "--dev-unhide"] == hidden
    assert args[-1] == "--cloak-off"  # cloaking was off before we came
    assert not (home / "hidhide-state.json").exists()


def test_state_survives_a_crash(hider):
    h, calls, home = hider
    h.hide(0x054C, 0x09CC)
    again = hide._WindowsHider()  # a new process after the old one was killed
    again.restore()
    assert "--dev-unhide" in calls[-1]
    assert not (home / "hidhide-state.json").exists()


def test_bluetooth_paths_match_and_virtual_pads_are_spared(hider, monkeypatch):
    h, calls, _ = hider
    bluetooth = json.dumps(
        [
            {
                "devices": [
                    {  # our own ViGEm DualShock 4: no parent bus
                        "deviceInstancePath": "HID\\VID_054C&PID_09CC&REV_0100\\2&1",
                        "baseContainerDeviceInstancePath": "",
                    },
                    {
                        "deviceInstancePath": "HID\\{00001124-0000-1000-8000-00805f9b34fb}_VID&0002054c_PID&09cc\\9&3",
                        "baseContainerDeviceInstancePath": "BTHENUM\\{00001124-0000-1000-8000-00805F9B34FB}_VID&0002054C_PID&09CC\\8&1",
                    },
                ]
            }
        ]
    )
    original = hide._WindowsHider._run
    monkeypatch.setattr(
        hide._WindowsHider, "_run", lambda self, *a: bluetooth if a == ("--dev-gaming",) else original(self, *a)
    )
    assert h.hide(0x054C, 0x09CC) == "hidden"
    args = calls[-1]
    hidden = [args[i + 1] for i, a in enumerate(args) if a == "--dev-hide"]
    assert len(hidden) == 2 and all("0002054" in p.upper() for p in hidden)


def test_unknown_pad_is_reported(hider):
    h, calls, _ = hider
    assert "does not list" in h.hide(0x1111, 0x2222)
