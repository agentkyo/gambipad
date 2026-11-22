"""Command line entry points."""
from __future__ import annotations

import argparse
import sys
import time

from . import __version__, profile as profiles
from .driver import Driver, find_devices
from .engine import detect_ghosts
from .state import BUTTONS


def _driver(args, output: str | None = None) -> Driver:
    settings = profiles.load_settings()
    name = getattr(args, "profile", None) or settings["active_profile"]
    data = profiles.load_profile(name)
    if output:
        data["output"] = output
    if getattr(args, "no_hide", False):
        settings["hide_physical"] = False
    return Driver(data, settings)


def _wait_for_pad(driver: Driver, seconds: float = 5.0) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if driver.raw is not None:
            return True
        time.sleep(0.05)
    print("No supported controller found. Try `gambipad devices`.")
    return False


def cmd_devices(args) -> int:
    devices = find_devices(profiles.load_settings()["extra_devices"])
    if not devices:
        print("No supported controller found.")
        return 1
    for d in devices:
        bus = {1: "USB", 2: "Bluetooth"}.get(d.get("bus_type"), "?")
        print(f"{d['vendor_id']:04x}:{d['product_id']:04x}  {d.get('product_string') or '?'}  [{d['model']}]  {bus}")
    return 0


def cmd_run(args) -> int:
    driver = _driver(args)
    driver.start()
    print("GambiPad running. Ctrl+C to stop.")
    last = ""
    try:
        while True:
            time.sleep(0.5)
            if driver.status != last:
                last = driver.status
                print(f"[{last}]")
            if getattr(args, "seconds", 0) and time.monotonic() > args._end:
                break
    except KeyboardInterrupt:
        pass
    finally:
        driver.stop()
    return 0


def cmd_monitor(args) -> int:
    driver = _driver(args, output="none")
    driver.start()
    if not _wait_for_pad(driver):
        driver.stop()
        return 1
    print(f"{driver.device_name}: press buttons (Ctrl+C to stop)")
    end = time.monotonic() + args.seconds if args.seconds else None
    last = None
    try:
        while end is None or time.monotonic() < end:
            raw = driver.raw
            if raw is not None:
                view = (
                    tuple(sorted(raw.buttons)),
                    round(raw.lx, 1),
                    round(raw.ly, 1),
                    round(raw.rx, 1),
                    round(raw.ry, 1),
                    round(raw.l2, 1),
                    round(raw.r2, 1),
                    tuple((t.x // 40, t.y // 40) for t in raw.touches),
                )
                if view != last:
                    last = view
                    touches = " ".join(f"touch#{t.id}=({t.x},{t.y})" for t in raw.touches)
                    print(
                        f"{'+'.join(view[0]) or '-':32s} L({raw.lx:+.1f},{raw.ly:+.1f}) R({raw.rx:+.1f},{raw.ry:+.1f})"
                        f" L2={raw.l2:.1f} R2={raw.r2:.1f} {touches}"
                    )
            time.sleep(0.01)
    except KeyboardInterrupt:
        pass
    finally:
        driver.stop()
    return 0


def cmd_diagnose(args) -> int:
    driver = _driver(args, output="none")
    driver.start()
    if not _wait_for_pad(driver):
        driver.stop()
        return 1
    print(f"Press every button ONE AT A TIME for about a second each. Recording {args.seconds:.0f} s...")
    driver.start_capture()
    time.sleep(args.seconds)
    samples = driver.stop_capture()
    driver.stop()
    seen = sorted({b for s in samples for b in s}, key=BUTTONS.index)
    missing = [b for b in BUTTONS if b not in seen]
    ghosts = detect_ghosts(samples)
    print(f"Buttons seen: {', '.join(seen) or 'none'}")
    if missing:
        print(f"Never seen:   {', '.join(missing)}")
    if not ghosts:
        print("No ghost buttons found.")
        return 0
    for trigger, ghost in ghosts:
        print(f"GHOST: pressing '{trigger}' also reports '{ghost}'")
    if args.apply:
        settings = profiles.load_settings()
        data = profiles.load_profile(args.profile or settings["active_profile"])
        data["ghosts"] = ghosts
        print(f"Fix saved to {profiles.save_profile(data)}")
    else:
        print("Run again with --apply to save the fix into the profile.")
    return 0


def cmd_rumble(args) -> int:
    driver = _driver(args, output="none")
    driver.start()
    if not _wait_for_pad(driver):
        driver.stop()
        return 1
    for label, weak, strong in (("strong motor", 0, 255), ("weak motor", 255, 0)):
        print(label)
        driver.test_rumble(weak, strong, 1.0)
        time.sleep(1.4)
    driver.stop()
    return 0


def cmd_doctor(args) -> int:
    from .hide import create_hider
    from .outputs import NullPad, create_pad

    print(f"GambiPad {__version__} on {sys.platform}, Python {sys.version.split()[0]}")
    devices = find_devices(profiles.load_settings()["extra_devices"])
    print(f"controllers:      {len(devices)} found" + "".join(f"\n  - {d.get('product_string')} [{d['model']}]" for d in devices))
    try:
        pad = create_pad("xbox360", lambda weak, strong: None)
        print("virtual pad:      OK" if not isinstance(pad, NullPad) else "virtual pad:      unavailable")
        pad.close()
    except RuntimeError as error:
        print(f"virtual pad:      MISSING - {error}")
    print(f"hide physical:    {'available' if create_hider().available else 'not available (HidHide missing?)'}")
    print(f"config folder:    {profiles.config_dir()}")
    return 0


def cmd_off(args) -> int:
    from .power import power_off

    pads = [d for d in find_devices(profiles.load_settings()["extra_devices"]) if d.get("bus_type") == 2]
    if not pads:
        print("No Bluetooth controller connected (a cabled one cannot be switched off).")
        return 1
    done = [power_off(d.get("serial_number")) for d in pads]
    print("Controller switched off." if all(done) else "Could not switch the controller off.")
    return 0 if all(done) else 1


def cmd_unhide(args) -> int:
    from .hide import create_hider

    create_hider().restore()
    print("Controllers hidden by GambiPad are visible again.")
    return 0


def cmd_gui(args) -> int:
    from .gui.app import run

    return run()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="gambipad", description="Driver and configurator for DualShock 4 style pads and clones.")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command")
    p = sub.add_parser("gui", help="open the configuration window (default)")
    p.add_argument("--minimized", action="store_true", help="start hidden in the system tray")
    p.set_defaults(func=cmd_gui)
    p = sub.add_parser("run", help="run the driver without a window")
    p.add_argument("--profile")
    p.add_argument("--no-hide", action="store_true", help="do not hide the physical controller")
    p.add_argument("--seconds", type=float, default=0, help=argparse.SUPPRESS)
    p.set_defaults(func=cmd_run)
    sub.add_parser("devices", help="list supported controllers").set_defaults(func=cmd_devices)
    p = sub.add_parser("monitor", help="print what the controller reports")
    p.add_argument("--seconds", type=float, default=0)
    p.set_defaults(func=cmd_monitor)
    p = sub.add_parser("diagnose", help="find ghost buttons (one press also reporting another)")
    p.add_argument("--seconds", type=float, default=45)
    p.add_argument("--profile")
    p.add_argument("--apply", action="store_true", help="save the fix into the profile")
    p.set_defaults(func=cmd_diagnose)
    sub.add_parser("rumble", help="test both rumble motors").set_defaults(func=cmd_rumble)
    sub.add_parser("doctor", help="check the system requirements").set_defaults(func=cmd_doctor)
    sub.add_parser("off", help="switch a Bluetooth controller off").set_defaults(func=cmd_off)
    sub.add_parser("unhide", help="make the real controller visible again after a crash").set_defaults(func=cmd_unhide)
    args = parser.parse_args(argv)
    if getattr(args, "seconds", 0) and args.command == "run":
        args._end = time.monotonic() + args.seconds
    func = getattr(args, "func", cmd_gui)
    return func(args) or 0


def gui_main() -> int:
    return main(["gui"])


if __name__ == "__main__":
    sys.exit(main())
