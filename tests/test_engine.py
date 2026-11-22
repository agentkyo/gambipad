import pytest

from gambipad.engine import Engine, apply_ghosts, detect_ghosts, lightbar_color, shape_stick, shape_trigger
from gambipad.profile import default_profile, normalize
from gambipad.state import PadState, Touch


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def make(**changes):
    profile = default_profile()
    profile.update(changes)
    clock = Clock()
    return Engine(profile, clock), clock


def press(*names, **kw):
    return PadState(buttons=frozenset(names), **kw)


# ------------------------------------------------------------------- ghosts


def test_ghost_ps_removed_while_l1_held():
    engine, _ = make(ghosts=[["l1", "ps"], ["r1", "touchpad"]])
    assert engine.process(press("l1", "ps")).pad.buttons == {"l1"}
    assert engine.process(press("r1", "touchpad")).pad.buttons == {"r1"}


def test_real_ps_still_works_without_trigger():
    engine, _ = make(ghosts=[["l1", "ps"]])
    assert engine.process(press("ps")).pad.buttons == {"ps"}


def test_apply_ghosts_is_not_chained():
    assert apply_ghosts({"l1", "ps", "cross"}, [["l1", "ps"]]) == {"l1", "cross"}


def test_detect_ghosts_from_capture():
    samples = [frozenset()] * 50
    for single in ("cross", "circle", "l2", "r2", "share"):
        samples += [frozenset({single})] * 40
    samples += [frozenset({"l1", "ps"})] * 38
    samples += [frozenset({"r1", "touchpad"})] * 40
    assert detect_ghosts(samples) == [["l1", "ps"], ["r1", "touchpad"]]


def test_detect_ghosts_ignores_healthy_pad_and_chords():
    samples = [frozenset({"l1"})] * 30 + [frozenset({"ps"})] * 30 + [frozenset({"l1", "ps"})] * 30
    assert detect_ghosts(samples) == []
    assert detect_ghosts([frozenset({"cross", "ps"})] * 2) == []


# -------------------------------------------------------------------- remap


def test_identity_passthrough():
    engine, _ = make()
    frame = engine.process(press("cross", "up", lx=0.5))
    assert frame.pad.buttons == {"cross", "up"}
    assert frame.keys == frozenset()


def test_remap_to_other_button_key_and_mouse():
    profile = default_profile()
    profile["buttons"]["cross"] = {"type": "button", "to": ["pad:circle"]}
    profile["buttons"]["square"] = {"type": "button", "to": ["key:space", "mouse:left"]}
    profile["buttons"]["share"] = {"type": "none"}
    engine = Engine(profile, Clock())
    frame = engine.process(press("cross", "square", "share"))
    assert frame.pad.buttons == {"circle"}
    assert frame.keys == {"space"}
    assert frame.mouse_buttons == {"left"}


def test_wheel_ticks_once_per_press():
    profile = default_profile()
    profile["buttons"]["up"] = {"type": "button", "to": ["mouse:wheel_up"]}
    engine = Engine(profile, Clock())
    assert engine.process(press("up")).wheel == 1
    assert engine.process(press("up")).wheel == 0
    engine.process(press())
    assert engine.process(press("up")).wheel == 1


def test_turbo_pulses():
    profile = default_profile()
    profile["buttons"]["cross"] = {"type": "turbo", "to": ["pad:cross"], "hz": 10}
    clock = Clock()
    engine = Engine(profile, clock)
    seen = []
    for _ in range(20):
        seen.append("cross" in engine.process(press("cross")).pad.buttons)
        clock.now += 0.01
    assert seen[0] is True
    assert True in seen and False in seen
    assert sum(a != b for a, b in zip(seen, seen[1:])) == 3  # 10 Hz over 0.2 s
    assert "cross" not in engine.process(press()).pad.buttons


def test_toggle_latches():
    profile = default_profile()
    profile["buttons"]["l3"] = {"type": "toggle", "to": ["pad:l3"]}
    engine = Engine(profile, Clock())
    assert "l3" in engine.process(press("l3")).pad.buttons
    assert "l3" in engine.process(press()).pad.buttons
    assert "l3" not in engine.process(press("l3")).pad.buttons
    assert "l3" not in engine.process(press()).pad.buttons


# ------------------------------------------------------------------- combos


def test_combo_suppresses_its_buttons():
    profile = default_profile()
    profile["combos"] = [{"buttons": ["l3", "r3"], "action": {"type": "button", "to": ["key:f5"]}, "suppress": True}]
    engine = Engine(profile, Clock())
    frame = engine.process(press("l3", "r3", "cross"))
    assert frame.keys == {"f5"}
    assert frame.pad.buttons == {"cross"}
    assert engine.process(press("l3")).pad.buttons == {"l3"}


def test_combo_without_suppress_keeps_buttons():
    profile = default_profile()
    profile["combos"] = [{"buttons": ["l1", "r1"], "action": {"type": "button", "to": ["key:f1"]}, "suppress": False}]
    frame = Engine(profile, Clock()).process(press("l1", "r1"))
    assert frame.keys == {"f1"} and frame.pad.buttons == {"l1", "r1"}


def test_combo_swallows_trigger_analog():
    profile = default_profile()
    profile["combos"] = [{"buttons": ["l2", "cross"], "action": {"type": "button", "to": ["key:q"]}, "suppress": True}]
    frame = Engine(profile, Clock()).process(press("l2", "cross", l2=0.8))
    assert frame.pad.l2 == 0.0 and frame.pad.buttons == frozenset()


# ------------------------------------------------------------------- macros


def macro_profile(mode, steps):
    profile = default_profile()
    profile["macros"] = {"m": {"mode": mode, "steps": steps}}
    profile["buttons"]["triangle"] = {"type": "macro", "macro": "m"}
    return profile


def run(engine, clock, state, seconds, step=0.005):
    frames = []
    for _ in range(int(round(seconds / step))):
        frames.append(engine.process(state))
        clock.now += step
    return frames


def test_macro_once_plays_sequence_and_ends():
    steps = [{"tap": "pad:cross", "ms": 50}, {"wait": 50}, {"tap": "key:a", "ms": 50}]
    clock = Clock()
    engine = Engine(macro_profile("once", steps), clock)
    frames = run(engine, clock, press("triangle"), 0.05) + run(engine, clock, press(), 0.3)
    timeline = [(f.pad.buttons, f.keys) for f in frames]
    assert timeline[0] == ({"cross"}, frozenset())
    assert (frozenset(), frozenset()) in timeline
    assert (frozenset(), {"a"}) in timeline
    assert timeline[-1] == (frozenset(), frozenset())
    assert all("triangle" not in b for b, _ in timeline)


def test_macro_once_does_not_restart_while_running():
    steps = [{"tap": "pad:cross", "ms": 100}]
    clock = Clock()
    engine = Engine(macro_profile("once", steps), clock)
    engine.process(press("triangle"))
    clock.now += 0.02
    engine.process(press())
    clock.now += 0.02
    assert "cross" in engine.process(press("triangle")).pad.buttons
    clock.now += 0.07
    assert "cross" not in engine.process(press("triangle")).pad.buttons


def test_macro_hold_loops_and_stops_on_release():
    steps = [{"tap": "pad:cross", "ms": 20}, {"wait": 20}]
    clock = Clock()
    engine = Engine(macro_profile("hold", steps), clock)
    frames = run(engine, clock, press("triangle"), 0.4)
    presses = sum(1 for a, b in zip(frames, frames[1:]) if "cross" in b.pad.buttons and "cross" not in a.pad.buttons)
    assert 8 <= presses <= 11
    assert engine.process(press()).pad.buttons == frozenset()
    assert all(f.pad.buttons == frozenset() for f in run(engine, clock, press(), 0.2))


def test_macro_toggle_runs_until_pressed_again():
    steps = [{"tap": "key:e", "ms": 20}, {"wait": 20}]
    clock = Clock()
    engine = Engine(macro_profile("toggle", steps), clock)
    run(engine, clock, press("triangle"), 0.02)
    assert any(f.keys == {"e"} for f in run(engine, clock, press(), 0.3))
    run(engine, clock, press("triangle"), 0.02)
    assert all(f.keys == frozenset() for f in run(engine, clock, press(), 0.3))


def test_macro_without_waits_cannot_hang():
    clock = Clock()
    engine = Engine(macro_profile("hold", [{"press": "pad:cross"}, {"release": "pad:cross"}]), clock)
    for _ in range(50):
        engine.process(press("triangle"))
        clock.now += 0.004
    assert engine.process(press()).pad.buttons == frozenset()


def test_macro_press_left_down_is_released_at_end():
    clock = Clock()
    engine = Engine(macro_profile("once", [{"press": "key:w"}, {"wait": 30}]), clock)
    assert engine.process(press("triangle")).keys == {"w"}
    clock.now += 0.05
    assert engine.process(press()).keys == frozenset()


# ---------------------------------------------------------- sticks, triggers

STICK = {"deadzone": 0.1, "outer": 1.0, "curve": 1.0, "invert_x": False, "invert_y": False}


def test_stick_deadzone_and_rescale():
    assert shape_stick(0.05, 0.05, STICK) == (0.0, 0.0)
    x, y = shape_stick(1.0, 0.0, STICK)
    assert x == pytest.approx(1.0) and y == 0.0
    x, _ = shape_stick(0.55, 0.0, STICK)
    assert x == pytest.approx(0.5)


def test_stick_outer_curve_invert():
    x, _ = shape_stick(0.8, 0.0, dict(STICK, outer=0.8))
    assert x == pytest.approx(1.0)
    x, _ = shape_stick(0.55, 0.0, dict(STICK, curve=2.0))
    assert x == pytest.approx(0.25)
    assert shape_stick(0.5, -0.5, dict(STICK, invert_x=True, invert_y=True)) == pytest.approx(
        tuple(-v for v in shape_stick(0.5, -0.5, STICK))
    )


def test_stick_diagonal_never_exceeds_unit():
    x, y = shape_stick(1.0, 1.0, STICK)
    assert abs(x) <= 1.0 and abs(y) <= 1.0


def test_swap_sticks():
    profile = default_profile()
    profile["sticks"]["swap"] = True
    frame = Engine(profile, Clock()).process(PadState(lx=1.0))
    assert frame.pad.lx == 0.0 and frame.pad.rx == pytest.approx(1.0)


def test_trigger_shaping():
    cfg = {"deadzone": 0.2, "max": 0.8, "hair": False}
    assert shape_trigger(0.1, cfg) == 0.0
    assert shape_trigger(0.5, cfg) == pytest.approx(0.5)
    assert shape_trigger(0.9, cfg) == 1.0
    assert shape_trigger(0.21, dict(cfg, hair=True)) == 1.0


def test_trigger_analog_passthrough_and_remap():
    engine, _ = make()
    frame = engine.process(press("l2", l2=0.4))
    assert frame.pad.l2 == pytest.approx(0.4) and "l2" in frame.pad.buttons

    profile = default_profile()
    profile["buttons"]["cross"] = {"type": "button", "to": ["pad:r2"]}
    profile["buttons"]["l2"] = {"type": "button", "to": ["key:q"]}
    frame = Engine(profile, Clock()).process(press("cross", "l2", l2=0.9))
    assert frame.pad.r2 == 1.0 and "r2" in frame.pad.buttons
    assert frame.pad.l2 == 0.0 and frame.keys == {"q"}


# ----------------------------------------------------------------- touchpad


def test_touchpad_native_passes_touches():
    engine, _ = make()
    touch = (Touch(1, 100, 100),)
    assert engine.process(PadState(touches=touch)).pad.touches == touch


def test_touchpad_mouse_mode_moves_pointer():
    profile = default_profile()
    profile["touchpad"] = {"mode": "mouse", "sensitivity": 1.0}
    engine = Engine(profile, Clock())
    first = engine.process(PadState(touches=(Touch(1, 100, 100),)))
    second = engine.process(PadState(touches=(Touch(1, 150, 80),)))
    lifted = engine.process(PadState())
    again = engine.process(PadState(touches=(Touch(2, 900, 900),)))
    assert (first.mouse_dx, first.mouse_dy) == (0.0, 0.0)
    assert second.mouse_dx > 0 and second.mouse_dy < 0
    assert second.pad.touches == ()
    assert (lifted.mouse_dx, again.mouse_dx) == (0.0, 0.0)


def test_touchpad_buttons_mode_splits_halves():
    profile = default_profile()
    profile["touchpad"]["mode"] = "buttons"
    profile["buttons"]["touch_left"] = {"type": "button", "to": ["pad:share"]}
    profile["buttons"]["touch_right"] = {"type": "button", "to": ["pad:options"]}
    engine = Engine(profile, Clock())
    left = engine.process(press("touchpad", touches=(Touch(1, 200, 300),)))
    right = engine.process(press("touchpad", touches=(Touch(1, 1500, 300),)))
    assert left.pad.buttons == {"share"} and right.pad.buttons == {"options"}


def test_frozen_touch_is_dropped_until_it_moves():
    clock = Clock()
    engine = Engine(default_profile(), clock)
    ghost = PadState(touches=(Touch(0, 1, 649), Touch(40, 1210, 476)))
    assert len(engine.process(ghost).pad.touches) == 2  # not yet known to be frozen
    clock.now += 0.5
    assert engine.process(ghost).pad.touches == ()
    clock.now += 5
    assert engine.process(ghost).pad.touches == ()
    moved = PadState(touches=(Touch(0, 30, 640), Touch(40, 1210, 476)))
    assert [t.id for t in engine.process(moved).pad.touches] == [0]


def test_frozen_touch_filter_can_be_turned_off():
    profile = default_profile()
    profile["touchpad"]["drop_frozen"] = False
    clock = Clock()
    engine = Engine(profile, clock)
    still = PadState(touches=(Touch(0, 1, 649),))
    engine.process(still)
    clock.now += 5
    assert len(engine.process(still).pad.touches) == 1


# ------------------------------------------------------------ light, rumble


def test_lightbar_modes():
    cfg = {"mode": "static", "color": [10, 20, 30], "brightness": 0.5}
    assert lightbar_color(cfg, None, 0) == (5, 10, 15)
    assert lightbar_color(dict(cfg, mode="off"), None, 0) == (0, 0, 0)
    full = lightbar_color(dict(cfg, mode="battery", brightness=1.0), PadState(battery=100), 0)
    empty = lightbar_color(dict(cfg, mode="battery", brightness=1.0), PadState(battery=0), 0)
    assert full == (0, 255, 0) and empty == (255, 0, 0)
    a = lightbar_color(dict(cfg, mode="rainbow"), None, 0.0)
    b = lightbar_color(dict(cfg, mode="rainbow"), None, 2.0)
    assert a != b


def test_rumble_scaling():
    profile = default_profile()
    profile["rumble"] = {"enabled": True, "strong": 0.5, "weak": 2.0}
    engine = Engine(profile, Clock())
    assert engine.rumble(200, 200) == (255, 100)
    profile["rumble"]["enabled"] = False
    engine.set_profile(profile)
    assert engine.rumble(200, 200) == (0, 0)


# ------------------------------------------------------------------ profile


def test_normalize_survives_garbage():
    clean = normalize(
        {
            "name": "  x  ",
            "output": "nope",
            "ghosts": [["l1", "ps"], ["l1", "l1"], "bad", ["zz", "ps"]],
            "buttons": {"cross": {"type": "button", "to": "key:a"}, "circle": {"type": "macro", "macro": "missing"}, "zz": 1},
            "sticks": {"left": {"deadzone": 5, "curve": "x"}},
            "combos": [{"buttons": ["l1"], "action": {"type": "button", "to": ["key:a"]}}, 7],
            "macros": {"ok": {"mode": "weird", "steps": [{"tap": "key:a"}, {"tap": "bad"}, {"wait": -5}, 3]}},
        }
    )
    assert clean["name"] == "x" and clean["output"] == "xbox360"
    assert clean["ghosts"] == [["l1", "ps"]]
    assert clean["buttons"]["cross"] == {"type": "button", "to": ["key:a"]}
    assert clean["buttons"]["circle"] == {"type": "none"}
    assert clean["sticks"]["left"]["deadzone"] == 0.9 and clean["sticks"]["left"]["curve"] == 1.0
    assert clean["combos"] == []
    assert clean["macros"]["ok"] == {"mode": "once", "steps": [{"tap": "key:a", "ms": 50}, {"wait": 0}]}
    assert normalize(None) == default_profile()
    assert normalize(clean) == clean
