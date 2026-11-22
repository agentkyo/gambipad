"""The mapping engine: raw controller state in, desired outputs out.

Pure logic with an injectable clock, so every feature (ghost button filtering,
remaps, turbo, toggles, combos, macros, stick and trigger shaping, touchpad
modes) is unit tested without hardware.
"""
from __future__ import annotations

import colorsys
import math
import time
from typing import Callable

from .profile import normalize
from .state import TOUCH_WIDTH, Frame, PadState

MAX_OPS_PER_FRAME = 256
MIN_LOOP_SECONDS = 0.01
FROZEN_TOUCH_SECONDS = 0.3


def apply_ghosts(pressed: set[str], ghosts) -> set[str]:
    """Drop buttons a faulty pad reports together with another one.

    ``ghosts`` is a list of (trigger, ghost): while ``trigger`` is held, the
    ``ghost`` bit is not trusted and gets removed.
    """
    held = set(pressed)
    for trigger, ghost in ghosts:
        if trigger in pressed:
            held.discard(ghost)
    return held


def detect_ghosts(samples) -> list[list[str]]:
    """Find ghost pairs from samples taken while pressing one button at a time.

    A button B is a ghost of A when B was seen, but never without A, and A was
    never seen without B. That is exactly the signature of firmware that
    mirrors one bit into another.
    """
    seen: dict[str, int] = {}
    together: dict[tuple[str, str], int] = {}
    for sample in samples:
        for a in sample:
            seen[a] = seen.get(a, 0) + 1
            for b in sample:
                if a != b:
                    together[(a, b)] = together.get((a, b), 0) + 1
    pairs = []
    for (a, b), count in together.items():
        if count == seen[a] == seen[b] and count >= 3:
            pairs.append((a, b))
    # Each mirrored pair shows up twice (a,b) and (b,a). The ghost is the
    # system button: nobody presses PS or the touchpad as often as a shoulder.
    system = ("ps", "touchpad", "share", "options")
    result = []
    for a, b in pairs:
        if b in system and a not in system:
            result.append([a, b])
        elif a not in system and b not in system and a < b:
            result.append([a, b])
        elif a in system and b in system and a < b:
            result.append([a, b])
    return sorted(result)


def shape_stick(x: float, y: float, cfg: dict) -> tuple[float, float]:
    """Radial dead zone, outer limit and response curve."""
    magnitude = math.hypot(x, y)
    dead, outer = cfg["deadzone"], max(cfg["outer"], cfg["deadzone"] + 0.01)
    if magnitude <= dead:
        return 0.0, 0.0
    scaled = min(1.0, (magnitude - dead) / (outer - dead)) ** cfg["curve"]
    x, y = x / magnitude * scaled, y / magnitude * scaled
    if cfg["invert_x"]:
        x = -x
    if cfg["invert_y"]:
        y = -y
    return max(-1.0, min(1.0, x)), max(-1.0, min(1.0, y))


def shape_trigger(value: float, cfg: dict) -> float:
    dead, top = cfg["deadzone"], max(cfg["max"], cfg["deadzone"] + 0.01)
    if value <= dead:
        return 0.0
    if cfg["hair"]:
        return 1.0
    return min(1.0, (value - dead) / (top - dead))


def lightbar_color(cfg: dict, state: PadState | None, now: float) -> tuple[int, int, int]:
    mode = cfg["mode"]
    if mode == "off":
        return (0, 0, 0)
    if mode == "rainbow":
        rgb = colorsys.hsv_to_rgb((now / 6.0) % 1.0, 1.0, 1.0)
    elif mode == "battery" and state is not None and state.battery is not None:
        level = state.battery / 100.0
        rgb = (1.0 - level, level, 0.0)
    else:
        rgb = tuple(c / 255.0 for c in cfg["color"])
    return tuple(int(round(c * 255 * cfg["brightness"])) for c in rgb)


def compile_macro(steps: list[dict]) -> list[tuple[str, object]]:
    ops: list[tuple[str, object]] = []
    for step in steps:
        if "wait" in step:
            ops.append(("wait", step["wait"] / 1000.0))
        elif "stick" in step:
            ops.append(("stick", (step["stick"], None if step.get("off") else (step["x"], step["y"]))))
        elif "tap" in step:
            ops += [("press", step["tap"]), ("wait", step["ms"] / 1000.0), ("release", step["tap"])]
        elif "press" in step:
            ops.append(("press", step["press"]))
        elif "release" in step:
            ops.append(("release", step["release"]))
    return ops


class _MacroRun:
    def __init__(self, ops, mode: str, now: float):
        self.ops = ops
        self.mode = mode
        self.index = 0
        self.wake = now
        self.held: set[str] = set()
        self.sticks: dict[str, tuple[float, float]] = {}  # stick positions the macro is holding
        self.stop = False  # asked to finish (button released / toggled off)
        self.done = not ops
        total = sum(v for op, v in ops if op == "wait")
        self.pad_loop = max(0.0, MIN_LOOP_SECONDS - total)

    def advance(self, now: float) -> None:
        budget = MAX_OPS_PER_FRAME
        while not self.done and now >= self.wake and budget:
            budget -= 1
            if self.index >= len(self.ops):
                self.held.clear()
                self.sticks.clear()
                if self.mode == "once" or self.stop:
                    self.done = True
                    break
                self.index = 0
                self.wake += self.pad_loop
                continue
            op, value = self.ops[self.index]
            self.index += 1
            if op == "press":
                self.held.add(value)
            elif op == "release":
                self.held.discard(value)
            elif op == "stick":
                if value[1] is None:
                    self.sticks.pop(value[0], None)
                else:
                    self.sticks[value[0]] = value[1]
            else:
                self.wake += value
        if self.stop and self.mode != "once":
            # Looping macros end at once so nothing stays stuck down.
            self.held.clear()
            self.sticks.clear()
            self.done = True


class Engine:
    def __init__(self, profile: dict | None = None, clock: Callable[[], float] = time.monotonic):
        self.clock = clock
        self.set_profile(profile)

    def set_profile(self, profile: dict | None) -> None:
        self.profile = normalize(profile)
        self._macros = {n: (compile_macro(m["steps"]), m["mode"]) for n, m in self.profile["macros"].items()}
        self._prev_sources: set[str] = set()
        self._turbo_start: dict[str, float] = {}
        self._toggled: set[str] = set()
        self._runs: dict[str, _MacroRun] = {}
        self._prev_targets: set[str] = set()
        self._prev_touch = None
        self._stick_override: dict[str, tuple[float, float]] = {}
        self._touch_seen: dict[int, tuple[tuple[int, int], float]] = {}

    # ------------------------------------------------------------------ steps

    def _live_touches(self, touches, now: float):
        """Drop touches that never move.

        Some clones have no touch sensor and report a finger frozen at a fixed
        spot forever. A real finger always jitters by a unit or two.
        """
        if not self.profile["touchpad"]["drop_frozen"]:
            return touches
        seen: dict[int, tuple[tuple[int, int], float]] = {}
        live = []
        for touch in touches:
            position, since = self._touch_seen.get(touch.id, (None, now))
            if position != (touch.x, touch.y):
                since = now
            seen[touch.id] = ((touch.x, touch.y), since)
            if now - since < FROZEN_TOUCH_SECONDS:
                live.append(touch)
        self._touch_seen = seen
        return tuple(live)

    def _sources(self, raw: PadState, touches) -> tuple[set[str], dict[str, dict]]:
        profile = self.profile
        pressed = apply_ghosts(set(raw.buttons), profile["ghosts"])
        mode = profile["touchpad"]["mode"]
        if mode == "buttons" and "touchpad" in pressed:
            pressed.discard("touchpad")
            right = bool(touches) and touches[0].x >= TOUCH_WIDTH // 2
            pressed.add("touch_right" if right else "touch_left")

        actions = dict(profile["buttons"])
        consumed: set[str] = set()
        active: set[str] = set()
        for index, combo in enumerate(profile["combos"]):
            if all(b in pressed for b in combo["buttons"]):
                name = f"combo:{index}"
                active.add(name)
                actions[name] = combo["action"]
                if combo["suppress"]:
                    consumed.update(combo["buttons"])
        return (pressed - consumed) | active, actions

    def _targets(self, sources: set[str], actions: dict[str, dict], now: float) -> dict[str, set[str]]:
        """Map every active output target to the sources holding it."""
        targets: dict[str, set[str]] = {}

        def hold(target_list, source):
            for target in target_list:
                targets.setdefault(target, set()).add(source)

        rising = sources - self._prev_sources
        falling = self._prev_sources - sources

        for source in falling:
            self._turbo_start.pop(source, None)
            run = self._runs.get(source)
            if run and run.mode == "hold":
                run.stop = True

        for source in sources:
            action = actions.get(source, {"type": "none"})
            kind = action["type"]
            if kind == "button":
                hold(action["to"], source)
            elif kind == "turbo":
                start = self._turbo_start.setdefault(source, now)
                if int((now - start) * action["hz"] * 2) % 2 == 0:
                    hold(action["to"], source)
            elif kind == "toggle" and source in rising:
                self._toggled.symmetric_difference_update({source})
            elif kind == "macro" and source in rising:
                self._start_macro(source, action["macro"], now)

        for source in list(self._toggled):
            action = actions.get(source) or self.profile["buttons"].get(source)
            if not action or action["type"] != "toggle":
                self._toggled.discard(source)
                continue
            hold(action["to"], source)

        self._stick_override = {}
        for source, run in list(self._runs.items()):
            run.advance(now)
            hold(run.held, f"macro:{source}")
            self._stick_override.update(run.sticks)
            if run.done:
                del self._runs[source]
        return targets

    def _start_macro(self, source: str, name: str, now: float) -> None:
        if name not in self._macros:
            return
        ops, mode = self._macros[name]
        running = self._runs.get(source)
        if running and not running.done:
            if mode == "toggle":
                running.stop = True
            return
        self._runs[source] = _MacroRun(ops, mode, now)

    # ---------------------------------------------------------------- process

    def process(self, raw: PadState) -> Frame:
        now = self.clock()
        profile = self.profile
        touches = self._live_touches(raw.touches, now)
        sources, actions = self._sources(raw, touches)
        targets = self._targets(sources, actions, now)
        self._prev_sources = sources

        active = set(targets)
        newly = active - self._prev_targets
        self._prev_targets = active
        wheel = int("mouse:wheel_up" in newly) - int("mouse:wheel_down" in newly)

        pad_buttons = {t[4:] for t in active if t.startswith("pad:")}
        keys = frozenset(t[4:] for t in active if t.startswith("key:"))
        mouse = frozenset(t[6:] for t in active if t.startswith("mouse:") and not t.startswith("mouse:wheel"))

        sticks = profile["sticks"]
        left = shape_stick(raw.lx, raw.ly, sticks["left"])
        right = shape_stick(raw.rx, raw.ry, sticks["right"])
        if sticks["swap"]:
            left, right = right, left
        # A running macro can take over a stick (aiming a kick, for instance).
        left = self._stick_override.get("left", left)
        right = self._stick_override.get("right", right)

        analog = {}
        for side, value in (("l2", raw.l2), ("r2", raw.r2)):
            target = f"pad:{side}"
            action = profile["buttons"][side]
            identity = action["type"] == "button" and target in action["to"]
            others = targets.get(target, set()) - {side}
            if others:
                analog[side] = 1.0
            elif identity and side in sources:  # not swallowed by a combo
                analog[side] = shape_trigger(value, profile["triggers"][side])
            else:
                analog[side] = 0.0
            pad_buttons.discard(side)
            if analog[side] > 0:
                pad_buttons.add(side)

        touch_mode = profile["touchpad"]["mode"]
        dx = dy = 0.0
        touch = touches[0] if touches else None
        if touch_mode == "mouse" and touch and self._prev_touch and self._prev_touch.id == touch.id:
            gain = profile["touchpad"]["sensitivity"] * 0.6
            dx = (touch.x - self._prev_touch.x) * gain
            dy = (touch.y - self._prev_touch.y) * gain
        self._prev_touch = touch

        pad = PadState(
            buttons=frozenset(pad_buttons),
            lx=left[0],
            ly=left[1],
            rx=right[0],
            ry=right[1],
            l2=analog["l2"],
            r2=analog["r2"],
            touches=touches if touch_mode == "native" else (),
            gyro=raw.gyro,
            accel=raw.accel,
            battery=raw.battery,
            charging=raw.charging,
        )
        return Frame(pad=pad, keys=keys, mouse_buttons=mouse, mouse_dx=dx, mouse_dy=dy, wheel=wheel)

    def rumble(self, weak: int, strong: int) -> tuple[int, int]:
        """Scale a rumble request from the game by the profile settings."""
        cfg = self.profile["rumble"]
        if not cfg["enabled"]:
            return 0, 0
        return (min(255, int(weak * cfg["weak"])), min(255, int(strong * cfg["strong"])))
