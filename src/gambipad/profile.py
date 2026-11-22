"""Profiles: plain JSON documents describing how one controller should behave.

A profile is kept as a dict so the GUI, the engine and the files on disk all
share one shape. ``normalize`` is the single place that fills defaults and
throws away anything malformed, so the engine can trust what it receives.
"""
from __future__ import annotations

import copy
import json
import os
import re
import sys
from pathlib import Path

from .state import BUTTONS, TOUCH_BUTTONS

APP_NAME = "GambiPad"

ACTION_TYPES = ("button", "none", "turbo", "toggle", "macro")
OUTPUTS = ("xbox360", "ds4", "none")
LIGHT_MODES = ("static", "battery", "rainbow", "off")
TOUCH_MODES = ("native", "mouse", "buttons", "off")
MACRO_MODES = ("once", "hold", "toggle")
MOUSE_TARGETS = ("left", "right", "middle", "wheel_up", "wheel_down")

#: Buttons that can carry an action (physical ones plus touchpad halves).
SOURCES: tuple[str, ...] = BUTTONS + TOUCH_BUTTONS

_TARGET_RE = re.compile(r"^(pad|key|mouse):([a-z0-9_]+)$")


def is_target(value) -> bool:
    if not isinstance(value, str):
        return False
    match = _TARGET_RE.match(value)
    if not match:
        return False
    kind, name = match.groups()
    if kind == "pad":
        return name in BUTTONS
    if kind == "mouse":
        return name in MOUSE_TARGETS
    return True


def _identity(name: str) -> dict:
    return {"type": "button", "to": [f"pad:{name}"]}


def default_profile(name: str = "Default") -> dict:
    buttons = {b: _identity(b) for b in BUTTONS}
    buttons["touch_left"] = {"type": "button", "to": ["mouse:left"]}
    buttons["touch_right"] = {"type": "button", "to": ["mouse:right"]}
    stick = {"deadzone": 0.06, "outer": 1.0, "curve": 1.0, "invert_x": False, "invert_y": False}
    trigger = {"deadzone": 0.0, "max": 1.0, "hair": False}
    return {
        "name": name,
        "output": "xbox360",
        "ghosts": [],
        "buttons": buttons,
        "sticks": {"left": dict(stick), "right": dict(stick), "swap": False},
        "triggers": {"l2": dict(trigger), "r2": dict(trigger)},
        "lightbar": {"mode": "static", "color": [0, 80, 255], "brightness": 1.0},
        "rumble": {"enabled": True, "strong": 1.0, "weak": 1.0},
        "touchpad": {"mode": "native", "sensitivity": 1.0, "drop_frozen": True},
        "combos": [],
        "macros": {},
    }


def _num(value, default: float, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return max(low, min(high, float(value)))


def _targets(value) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [t for t in value if is_target(t)]


def normalize_action(action, macros: dict | None = None) -> dict:
    if not isinstance(action, dict) or action.get("type") not in ACTION_TYPES:
        return {"type": "none"}
    kind = action["type"]
    if kind == "none":
        return {"type": "none"}
    if kind == "macro":
        name = action.get("macro")
        if not isinstance(name, str) or (macros is not None and name not in macros):
            return {"type": "none"}
        return {"type": "macro", "macro": name}
    out = {"type": kind, "to": _targets(action.get("to"))}
    if not out["to"]:
        return {"type": "none"}
    if kind == "turbo":
        out["hz"] = _num(action.get("hz"), 12.0, 1.0, 30.0)
    return out


def normalize_steps(steps) -> list[dict]:
    out: list[dict] = []
    for step in steps if isinstance(steps, list) else []:
        if not isinstance(step, dict):
            continue
        if "wait" in step:
            out.append({"wait": int(_num(step["wait"], 50, 0, 60000))})
        elif step.get("stick") in ("left", "right"):
            if step.get("off"):
                out.append({"stick": step["stick"], "off": True})
            else:
                x, y = _num(step.get("x"), 0.0, -1.0, 1.0), _num(step.get("y"), 0.0, -1.0, 1.0)
                out.append({"stick": step["stick"], "x": round(x, 3), "y": round(y, 3)})
        elif is_target(step.get("tap")):
            out.append({"tap": step["tap"], "ms": int(_num(step.get("ms"), 50, 20, 10000))})
        elif is_target(step.get("press")):
            out.append({"press": step["press"]})
        elif is_target(step.get("release")):
            out.append({"release": step["release"]})
    return out


def normalize(data) -> dict:
    """Return a complete, valid profile built from whatever ``data`` holds."""
    base = default_profile()
    if not isinstance(data, dict):
        return base
    out = copy.deepcopy(base)
    if isinstance(data.get("name"), str) and data["name"].strip():
        out["name"] = data["name"].strip()[:60]
    if data.get("output") in OUTPUTS:
        out["output"] = data["output"]

    ghosts = []
    for pair in data.get("ghosts") or []:
        if (
            isinstance(pair, (list, tuple))
            and len(pair) == 2
            and pair[0] in BUTTONS
            and pair[1] in BUTTONS
            and pair[0] != pair[1]
            and list(pair) not in ghosts
        ):
            ghosts.append(list(pair))
    out["ghosts"] = ghosts

    macros = {}
    for name, macro in (data.get("macros") or {}).items() if isinstance(data.get("macros"), dict) else []:
        if not isinstance(name, str) or not name.strip() or not isinstance(macro, dict):
            continue
        mode = macro.get("mode") if macro.get("mode") in MACRO_MODES else "once"
        macros[name.strip()[:40]] = {"mode": mode, "steps": normalize_steps(macro.get("steps"))}
    out["macros"] = macros

    given = data.get("buttons") if isinstance(data.get("buttons"), dict) else {}
    for source in SOURCES:
        if source in given:
            out["buttons"][source] = normalize_action(given[source], macros)

    sticks = data.get("sticks") if isinstance(data.get("sticks"), dict) else {}
    for side in ("left", "right"):
        src = sticks.get(side) if isinstance(sticks.get(side), dict) else {}
        dst = out["sticks"][side]
        dst["deadzone"] = _num(src.get("deadzone"), dst["deadzone"], 0.0, 0.9)
        dst["outer"] = _num(src.get("outer"), dst["outer"], 0.2, 1.0)
        dst["curve"] = _num(src.get("curve"), dst["curve"], 0.3, 4.0)
        dst["invert_x"] = bool(src.get("invert_x", False))
        dst["invert_y"] = bool(src.get("invert_y", False))
    out["sticks"]["swap"] = bool(sticks.get("swap", False))

    triggers = data.get("triggers") if isinstance(data.get("triggers"), dict) else {}
    for side in ("l2", "r2"):
        src = triggers.get(side) if isinstance(triggers.get(side), dict) else {}
        dst = out["triggers"][side]
        dst["deadzone"] = _num(src.get("deadzone"), 0.0, 0.0, 0.9)
        dst["max"] = _num(src.get("max"), 1.0, 0.1, 1.0)
        dst["hair"] = bool(src.get("hair", False))

    light = data.get("lightbar") if isinstance(data.get("lightbar"), dict) else {}
    if light.get("mode") in LIGHT_MODES:
        out["lightbar"]["mode"] = light["mode"]
    color = light.get("color")
    if isinstance(color, (list, tuple)) and len(color) == 3:
        out["lightbar"]["color"] = [int(_num(c, 0, 0, 255)) for c in color]
    out["lightbar"]["brightness"] = _num(light.get("brightness"), 1.0, 0.0, 1.0)

    rumble = data.get("rumble") if isinstance(data.get("rumble"), dict) else {}
    out["rumble"]["enabled"] = bool(rumble.get("enabled", True))
    out["rumble"]["strong"] = _num(rumble.get("strong"), 1.0, 0.0, 2.0)
    out["rumble"]["weak"] = _num(rumble.get("weak"), 1.0, 0.0, 2.0)

    touch = data.get("touchpad") if isinstance(data.get("touchpad"), dict) else {}
    if touch.get("mode") in TOUCH_MODES:
        out["touchpad"]["mode"] = touch["mode"]
    out["touchpad"]["sensitivity"] = _num(touch.get("sensitivity"), 1.0, 0.1, 5.0)
    out["touchpad"]["drop_frozen"] = bool(touch.get("drop_frozen", True))

    combos = []
    for combo in data.get("combos") or []:
        if not isinstance(combo, dict):
            continue
        buttons = [b for b in combo.get("buttons") or [] if b in BUTTONS]
        buttons = list(dict.fromkeys(buttons))
        action = normalize_action(combo.get("action"), macros)
        if len(buttons) >= 2 and action["type"] != "none":
            combos.append({"buttons": buttons, "action": action, "suppress": bool(combo.get("suppress", True))})
    out["combos"] = combos
    return out


# --------------------------------------------------------------------- storage


def config_dir() -> Path:
    override = os.environ.get("GAMBIPAD_HOME")
    if override:
        return Path(override)
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / APP_NAME
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / APP_NAME.lower()


def profiles_dir() -> Path:
    path = config_dir() / "profiles"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _slug(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", name).strip("-")
    return slug or "profile"


def profile_path(name: str) -> Path:
    return profiles_dir() / f"{_slug(name)}.json"


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def save_profile(profile: dict) -> Path:
    clean = normalize(profile)
    path = profile_path(clean["name"])
    _write_json(path, clean)
    return path


def load_profile_file(path: Path) -> dict:
    return normalize(json.loads(Path(path).read_text(encoding="utf-8")))


def list_profiles() -> list[str]:
    names = []
    for path in sorted(profiles_dir().glob("*.json")):
        try:
            names.append(load_profile_file(path)["name"])
        except (OSError, ValueError):
            continue
    return names


def load_profile(name: str) -> dict:
    path = profile_path(name)
    if path.exists():
        try:
            return load_profile_file(path)
        except (OSError, ValueError):
            pass
    return default_profile(name)


def delete_profile(name: str) -> None:
    profile_path(name).unlink(missing_ok=True)


DEFAULT_SETTINGS = {"active_profile": "Default", "language": "", "extra_devices": [], "hide_physical": True}


def load_settings() -> dict:
    out = dict(DEFAULT_SETTINGS)
    try:
        data = json.loads((config_dir() / "settings.json").read_text(encoding="utf-8"))
        if isinstance(data, dict):
            out.update({k: v for k, v in data.items() if k in DEFAULT_SETTINGS})
    except (OSError, ValueError):
        pass
    return out


def save_settings(settings: dict) -> None:
    _write_json(config_dir() / "settings.json", {k: settings.get(k, v) for k, v in DEFAULT_SETTINGS.items()})
