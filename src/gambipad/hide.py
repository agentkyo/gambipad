"""Hide the physical controller from games so only the virtual one is seen.

Without this a game receives every press twice (real pad + virtual pad) and
keeps seeing the faulty signals GambiPad is there to remove.

* Windows: drives HidHide (https://github.com/nefarius/HidHide) through its
  CLI. Only entries GambiPad added are removed again on exit.
* Linux: grabs the kernel's evdev nodes of the pad (EVIOCGRAB).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HIDHIDE_URL = "https://github.com/nefarius/HidHide/releases/latest"


def _hidhide_cli() -> Path | None:
    found = shutil.which("HidHideCLI")
    if found:
        return Path(found)
    for root in (os.environ.get("ProgramFiles"), os.environ.get("ProgramW6432")):
        if root:
            path = Path(root) / "Nefarius Software Solutions" / "HidHide" / "x64" / "HidHideCLI.exe"
            if path.exists():
                return path
    return None


class _WindowsHider:
    def __init__(self):
        self.cli = _hidhide_cli()
        self._hidden: list[str] = []
        self._cloak_was_off = False
        self._load()

    @property
    def available(self) -> bool:
        return self.cli is not None

    # What we hid is written to disk, so a crash or a forced kill cannot leave
    # the controller invisible: the next start (or `gambipad unhide`) undoes it.
    @staticmethod
    def _state_file() -> Path:
        from .profile import config_dir

        return config_dir() / "hidhide-state.json"

    def _load(self) -> None:
        try:
            data = json.loads(self._state_file().read_text(encoding="utf-8"))
            self._hidden = [p for p in data.get("hidden", []) if isinstance(p, str)]
            self._cloak_was_off = bool(data.get("cloak_was_off"))
        except (OSError, ValueError, AttributeError):
            pass

    def _store(self) -> None:
        path = self._state_file()
        try:
            if self._hidden or self._cloak_was_off:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps({"hidden": self._hidden, "cloak_was_off": self._cloak_was_off}), encoding="utf-8")
            else:
                path.unlink(missing_ok=True)
        except OSError:
            pass

    def _run(self, *args: str) -> str:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        done = subprocess.run([str(self.cli), *args], capture_output=True, text=True, timeout=15, creationflags=flags)
        return done.stdout

    def hide(self, vid: int, pid: int) -> str:
        if not self.available:
            return f"HidHide is not installed, games will see both controllers. Get it from {HIDHIDE_URL}"
        needle = f"VID_{vid:04X}&PID_{pid:04X}"
        try:
            groups = json.loads(self._run("--dev-gaming") or "[]")
            state = self._run("--cloak-state", "--dev-list")
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            return f"HidHide did not answer ({error})"
        already = state.upper()
        wanted: list[str] = []
        for group in groups:
            for device in group.get("devices", []):
                for key in ("deviceInstancePath", "baseContainerDeviceInstancePath"):
                    path = device.get(key) or ""
                    if needle in path.upper() and path not in wanted:
                        wanted.append(path)
        if not wanted:
            return "HidHide does not list the controller"
        args: list[str] = []
        for exe in {sys.executable, getattr(sys, "_base_executable", sys.executable)}:
            args += ["--app-reg", str(Path(exe).resolve())]
        for path in wanted:
            if f'"{path.upper()}"' not in already:
                args += ["--dev-hide", path]
                if path not in self._hidden:
                    self._hidden.append(path)
        self._cloak_was_off = self._cloak_was_off or "--cloak-off" in state
        args.append("--cloak-on")
        self._store()
        try:
            self._run(*args)
        except (OSError, subprocess.SubprocessError) as error:
            return f"HidHide refused the change ({error})"
        return "hidden"

    def restore(self) -> None:
        if not self.available or not (self._hidden or self._cloak_was_off):
            return
        args: list[str] = []
        for path in self._hidden:
            args += ["--dev-unhide", path]
        if self._cloak_was_off:
            args.append("--cloak-off")
        try:
            self._run(*args)
        except (OSError, subprocess.SubprocessError):
            return
        self._hidden.clear()
        self._cloak_was_off = False
        self._store()


class _LinuxHider:
    available = True

    def __init__(self):
        self._grabbed = []

    def hide(self, vid: int, pid: int) -> str:
        try:
            import evdev
        except ImportError:
            return "python-evdev is not installed, games will see both controllers"
        for path in evdev.list_devices():
            try:
                device = evdev.InputDevice(path)
                if device.info.vendor == vid and device.info.product == pid:
                    device.grab()
                    self._grabbed.append(device)
                else:
                    device.close()
            except OSError:
                continue
        return "hidden" if self._grabbed else "no kernel input nodes to grab"

    def restore(self) -> None:
        for device in self._grabbed:
            try:
                device.ungrab()
                device.close()
            except OSError:
                pass
        self._grabbed.clear()


class _NoHider:
    available = False

    def hide(self, vid: int, pid: int) -> str:
        return "hiding is not supported on this platform"

    def restore(self) -> None:
        pass


def create_hider():
    if sys.platform == "win32":
        return _WindowsHider()
    if sys.platform.startswith("linux"):
        return _LinuxHider()
    return _NoHider()
