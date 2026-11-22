# Profile format

A profile is one JSON file. Anything missing or invalid falls back to the default,
so a profile can be as small as `{"name": "Mine", "ghosts": [["l1", "ps"]]}`.

```json
{
  "name": "FC 26",
  "output": "xbox360",
  "ghosts": [["l1", "ps"], ["r1", "touchpad"]],
  "buttons": {
    "cross":  {"type": "button", "to": ["pad:cross"]},
    "share":  {"type": "turbo",  "to": ["pad:cross"], "hz": 12},
    "l3":     {"type": "toggle", "to": ["pad:l3"]},
    "r3":     {"type": "macro",  "macro": "skill"},
    "options": {"type": "button", "to": ["key:esc"]},
    "ps":     {"type": "none"}
  },
  "sticks": {
    "left":  {"deadzone": 0.06, "outer": 1.0, "curve": 1.0, "invert_x": false, "invert_y": false},
    "right": {"deadzone": 0.06, "outer": 1.0, "curve": 1.0, "invert_x": false, "invert_y": false},
    "swap": false
  },
  "triggers": {
    "l2": {"deadzone": 0.0, "max": 1.0, "hair": false},
    "r2": {"deadzone": 0.0, "max": 1.0, "hair": false}
  },
  "lightbar": {"mode": "static", "color": [0, 80, 255], "brightness": 1.0},
  "rumble": {"enabled": true, "strong": 1.0, "weak": 1.0},
  "touchpad": {"mode": "native", "sensitivity": 1.0, "drop_frozen": true},
  "combos": [
    {"buttons": ["l3", "r3"], "action": {"type": "button", "to": ["key:f12"]}, "suppress": true}
  ],
  "macros": {
    "skill": {
      "mode": "once",
      "steps": [{"tap": "pad:r1", "ms": 60}, {"wait": 40}, {"tap": "pad:cross", "ms": 60}]
    }
  }
}
```

## Names

**Buttons**: `cross circle square triangle l1 r1 l2 r2 share options ps touchpad l3 r3 up down left right`.
With `touchpad.mode` set to `buttons`, the click becomes `touch_left` or `touch_right`.

**Targets** (what an action sends):

- `pad:<button>` - a button on the virtual controller
- `key:<name>` - `a`-`z`, `0`-`9`, `f1`-`f12`, `space enter esc tab backspace delete insert home end
  pageup pagedown up down left right shift ctrl alt win capslock minus equal comma period slash
  semicolon quote lbracket rbracket backslash grave printscreen volume_up volume_down mute
  play_pause next_track prev_track`
- `mouse:<name>` - `left right middle wheel_up wheel_down`

## Fields

| Field | Values |
|---|---|
| `output` | `xbox360`, `ds4` (Windows only), `none` |
| `ghosts` | list of `[trigger, ghost]`: while `trigger` is held, `ghost` is ignored |
| action `type` | `button`, `turbo` (`hz` 1-30), `toggle`, `macro`, `none` |
| `sticks.*.deadzone` | 0-0.9, radial |
| `sticks.*.outer` | 0.2-1, tilt that already counts as full |
| `sticks.*.curve` | 0.3-4, exponent; 1 is linear |
| `triggers.*.hair` | any press past the dead zone is a full press |
| `lightbar.mode` | `static`, `battery`, `rainbow`, `off` |
| `rumble.strong` / `weak` | 0-2 multiplier per motor |
| `touchpad.mode` | `native`, `mouse`, `buttons`, `off` |
| `touchpad.drop_frozen` | ignore touches whose position never changes (clones without a touch sensor) |
| macro `mode` | `once`, `hold` (repeat while held), `toggle` (repeat until pressed again) |
| macro steps | `{"tap": target, "ms": n}`, `{"press": target}`, `{"release": target}`, `{"wait": ms}`, `{"stick": "left"\|"right", "x": -1..1, "y": -1..1}` (hold a stick position; Y grows downwards), `{"stick": "left"\|"right", "off": true}` (give the stick back) |

Anything a macro leaves pressed, and any stick it holds, is released when the macro ends.
