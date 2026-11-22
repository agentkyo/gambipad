## Install

**Windows** - download `GambiPad-Setup-<version>.exe` below and run it. It installs for your
user only (no administrator prompt) and offers to open the download pages of
[ViGEmBus](https://github.com/nefarius/ViGEmBus/releases/latest) and
[HidHide](https://github.com/nefarius/HidHide/releases/latest) if they are missing.
The executable is not code-signed, so Windows SmartScreen asks for confirmation the first
time ("More info" then "Run anyway"). The `portable.zip` is the same program without an installer.

**Linux** (Arch / CachyOS, Ubuntu / Zorin OS / Debian, Fedora, Bazzite):

```
curl -fsSL https://raw.githubusercontent.com/agentkyo/gambipad/main/install.sh | bash
```

## What is tested

Windows 11 with a DualShock 4 clone over USB and Bluetooth, on real hardware. The Linux
installer is exercised automatically on Ubuntu, Fedora and Arch images, but GambiPad has
not been run with a controller on Linux yet - reports are welcome.
