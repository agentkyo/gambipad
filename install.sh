#!/usr/bin/env bash
# GambiPad installer for Linux.
#
#   curl -fsSL https://raw.githubusercontent.com/agentkyo/gambipad/main/install.sh | bash
#
# Works on Arch / CachyOS, Debian / Ubuntu / Zorin OS, Fedora and on the
# image-based Fedora variants (Bazzite, Silverblue, Kinoite) where system
# packages cannot simply be installed.
#
# Everything goes into your home folder (a private Python environment). The only
# step that needs root is the udev rule that lets you read the controller and
# create the virtual one.
#
#   install.sh --autostart     also start GambiPad when you log in
#   install.sh --no-system     never touch system packages or udev (asks for no password)
#   install.sh --uninstall     remove everything again
#
# Environment: GAMBIPAD_SOURCE (pip source, default: the main branch on GitHub).

set -euo pipefail

SOURCE="${GAMBIPAD_SOURCE:-https://github.com/agentkyo/gambipad/archive/refs/heads/main.tar.gz}"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
PREFIX="$DATA/gambipad"
VENV="$PREFIX/venv"
BIN="$HOME/.local/bin"
DESKTOP="$DATA/applications/gambipad.desktop"
ICON="$DATA/icons/hicolor/256x256/apps/gambipad.png"
AUTOSTART="${XDG_CONFIG_HOME:-$HOME/.config}/autostart/gambipad.desktop"
RULE="/etc/udev/rules.d/70-gambipad.rules"

AUTOSTART_WANTED=0
SYSTEM=1
UNINSTALL=0
for arg in "$@"; do
    case "$arg" in
        --autostart) AUTOSTART_WANTED=1 ;;
        --no-system) SYSTEM=0 ;;
        --uninstall) UNINSTALL=1 ;;
        -h|--help) sed -n '2,20p' "$0" 2>/dev/null || true; exit 0 ;;
        *) echo "unknown option: $arg" >&2; exit 2 ;;
    esac
done

say() { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m  %s\n' "$*" >&2; }

# Run a command as root: directly when we are root, through sudo otherwise.
as_root() {
    if [ "$(id -u)" -eq 0 ]; then
        "$@"
    elif command -v sudo >/dev/null 2>&1; then
        sudo "$@"
    else
        return 1
    fi
}

if [ "$UNINSTALL" -eq 1 ]; then
    say "Removing GambiPad"
    [ -x "$VENV/bin/gambipad" ] && "$VENV/bin/gambipad" unhide >/dev/null 2>&1 || true
    rm -rf "$PREFIX" "$BIN/gambipad" "$DESKTOP" "$ICON" "$AUTOSTART"
    if [ "$SYSTEM" -eq 1 ] && [ -e "$RULE" ]; then
        as_root rm -f "$RULE" && as_root udevadm control --reload 2>/dev/null || warn "could not remove $RULE"
    fi
    say "Done. Your profiles in ${XDG_CONFIG_HOME:-$HOME/.config}/gambipad were kept."
    exit 0
fi

# ------------------------------------------------------------------ distro

ID_ALL=""
if [ -r /etc/os-release ]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    ID_ALL=" ${ID:-} ${ID_LIKE:-} "
fi
IMMUTABLE=0
if [ -e /run/ostree-booted ] || command -v rpm-ostree >/dev/null 2>&1; then
    IMMUTABLE=1  # Bazzite, Silverblue, Kinoite: the system image is read-only
fi

install_system_packages() {
    if [ "$SYSTEM" -eq 0 ]; then
        say "Skipping system packages (--no-system)"
        return
    fi
    if [ "$IMMUTABLE" -eq 1 ]; then
        say "Image-based system detected: using only what is already installed"
        return
    fi
    case "$ID_ALL" in
        *" arch "*|*" cachyos "*)
            say "Installing system packages with pacman"
            as_root pacman -S --needed --noconfirm python python-pip gcc linux-api-headers libxcb xcb-util-cursor libxkbcommon || warn "pacman step failed"
            ;;
        *" debian "*|*" ubuntu "*)
            say "Installing system packages with apt"
            as_root apt-get update -qq || true
            as_root env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
                python3 python3-venv python3-dev gcc linux-libc-dev \
                libegl1 libgl1 libxkbcommon0 libxkbcommon-x11-0 libdbus-1-3 libfontconfig1 libxcb-cursor0 \
                || warn "apt step failed"
            ;;
        *" fedora "*|*" rhel "*)
            say "Installing system packages with dnf"
            as_root dnf install -y python3 python3-pip python3-devel gcc kernel-headers \
                libxkbcommon libxkbcommon-x11 xcb-util-cursor mesa-libEGL fontconfig || warn "dnf step failed"
            ;;
        *)
            warn "Unknown distribution: skipping system packages. Python 3.11+ is required."
            ;;
    esac
}

install_system_packages

PYTHON="$(command -v python3 || command -v python || true)"
if [ -z "$PYTHON" ]; then
    echo "Python 3 was not found. Install it and run this script again." >&2
    exit 1
fi
if ! "$PYTHON" -c 'import sys; sys.exit(sys.version_info < (3, 11))'; then
    echo "GambiPad needs Python 3.11 or newer; found $("$PYTHON" -V 2>&1)." >&2
    exit 1
fi

# ------------------------------------------------------------- python side

say "Creating the Python environment in $VENV"
mkdir -p "$PREFIX" "$BIN"
rm -rf "$VENV"
"$PYTHON" -m venv "$VENV"
PIP="$VENV/bin/pip"
"$PIP" install --quiet --upgrade pip

say "Installing GambiPad and its libraries (this downloads about 200 MB)"
"$PIP" install --quiet hidapi PySide6
# python-evdev compiles against the kernel headers. Where there is no compiler
# (Bazzite and friends) the prebuilt evdev-binary package provides the same module.
if ! "$PIP" install --quiet evdev 2>/dev/null; then
    warn "could not compile evdev, using the prebuilt evdev-binary package"
    "$PIP" install --quiet evdev-binary
fi
"$PIP" install --quiet --no-deps "$SOURCE"

ln -sf "$VENV/bin/gambipad" "$BIN/gambipad"

# ------------------------------------------------------------ desktop entry

mkdir -p "$(dirname "$DESKTOP")" "$(dirname "$ICON")"
"$VENV/bin/gambipad" icon "$ICON" --size 256 >/dev/null 2>&1 || warn "could not write the icon"
cat > "$DESKTOP" <<EOF
[Desktop Entry]
Type=Application
Name=GambiPad
Comment=Driver and configurator for DualShock 4 style controllers and clones
Comment[pt_BR]=Driver e configurador para controles no padrão DualShock 4 e clones
Exec=$VENV/bin/gambipad gui
Icon=gambipad
Terminal=false
Categories=Game;Settings;HardwareSettings;
Keywords=gamepad;controller;joystick;dualshock;ps4;
EOF
if [ "$AUTOSTART_WANTED" -eq 1 ]; then
    mkdir -p "$(dirname "$AUTOSTART")"
    sed 's|^Exec=.*|& --minimized|' "$DESKTOP" > "$AUTOSTART"
    say "GambiPad will start with your session"
fi
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$(dirname "$DESKTOP")" >/dev/null 2>&1 || true

# --------------------------------------------------------------- udev rule

install_udev_rule() {
    local tmp
    tmp="$(mktemp)"
    cat > "$tmp" <<'EOF'
# GambiPad - lets the logged-in user read DualShock 4 style pads over hidraw
# and create the virtual controller through uinput.
KERNEL=="hidraw*", ATTRS{idVendor}=="054c", ATTRS{idProduct}=="05c4", MODE="0660", TAG+="uaccess"
KERNEL=="hidraw*", ATTRS{idVendor}=="054c", ATTRS{idProduct}=="09cc", MODE="0660", TAG+="uaccess"
KERNEL=="hidraw*", ATTRS{idVendor}=="054c", ATTRS{idProduct}=="0ba0", MODE="0660", TAG+="uaccess"
KERNEL=="hidraw*", KERNELS=="*054C:05C4*", MODE="0660", TAG+="uaccess"
KERNEL=="hidraw*", KERNELS=="*054C:09CC*", MODE="0660", TAG+="uaccess"
KERNEL=="uinput", SUBSYSTEM=="misc", MODE="0660", TAG+="uaccess", OPTIONS+="static_node=uinput"
EOF
    if as_root mkdir -p "$(dirname "$RULE")" && as_root install -m 0644 "$tmp" "$RULE"; then
        as_root udevadm control --reload >/dev/null 2>&1 || true
        as_root udevadm trigger >/dev/null 2>&1 || true
        say "udev rule installed: unplug and replug the controller"
    else
        warn "could not install the udev rule. Without it GambiPad cannot read the controller."
        warn "run later:  sudo install -m 0644 <the rule from packaging/linux/70-gambipad.rules> $RULE"
    fi
    rm -f "$tmp"
}

if [ "$SYSTEM" -eq 1 ]; then
    say "Installing the udev rule (this is the step that may ask for your password)"
    install_udev_rule
else
    warn "udev rule not installed (--no-system): GambiPad may not be able to read the controller"
fi

# ------------------------------------------------------------------- done

say "GambiPad $("$VENV/bin/gambipad" --version) installed"
case ":$PATH:" in
    *":$BIN:"*) echo "    Start it from the applications menu or run: gambipad" ;;
    *) echo "    Start it from the applications menu or run: $BIN/gambipad"
       echo "    ($BIN is not in your PATH)" ;;
esac
echo "    Check the system with: $BIN/gambipad doctor"
