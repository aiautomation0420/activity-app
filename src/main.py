"""Main entrypoint: tie power, scheduler, cursor, keys, exclusions, and hotkeys together."""

from __future__ import annotations

import argparse
import logging
import os
import random
import signal
import sys
import threading
import time
from typing import List

from src.cursor import click_in_place, move_cursor_safe, scroll_safe
from src.exclusions import cycle_apps, cycle_tabs
from src.hotkeys import HotkeyManager
from src.keys import natural_typing, perform_safe_key_action, silent_keys
from src.power import PowerManager
from src.scheduler import Intensity, Scheduler

LOG_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "reminder")
LOG_FILE = os.path.join(LOG_DIR, "reminder.log")
LOG_FMT = "%(asctime)s [%(levelname)s] %(message)s"

os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(filename=LOG_FILE, level=logging.INFO, format=LOG_FMT)
console = logging.StreamHandler(sys.stdout)
console.setLevel(logging.INFO)
console.setFormatter(logging.Formatter(LOG_FMT))
logging.getLogger().addHandler(console)


def _build_scheduler(intensity: str) -> Scheduler:
    if intensity == Intensity.LOW:
        return Scheduler(
            intensity=intensity,
            min_delay=3.0,
            max_delay=12.0,
            micro_break_every=600.0,
            micro_break_duration=60.0,
            short_pause_every=90.0,
            short_pause_duration=(30.0, 90.0),
        )
    if intensity == Intensity.HIGH:
        return Scheduler(
            intensity=intensity,
            min_delay=1.0,
            max_delay=5.0,
            micro_break_every=300.0,
            micro_break_duration=30.0,
            short_pause_every=60.0,
            short_pause_duration=(15.0, 60.0),
        )
    return Scheduler(
        intensity=intensity,
        min_delay=2.0,
        max_delay=8.0,
        micro_break_every=600.0,
        micro_break_duration=45.0,
        short_pause_every=120.0,
        short_pause_duration=(30.0, 120.0),
    )


def _keys(advanced: bool) -> str:
    if advanced:
        natural_typing()
        return "typing"
    return f"key:{silent_keys()}"


# Per-action toggles used by the GUI; each returns a short label for the log.
ACTIONS = {
    "move": lambda advanced: "move(%d,%d)" % move_cursor_safe(),
    "click": lambda advanced: "click(%d,%d)" % click_in_place(),
    "scroll": lambda advanced: scroll_safe() or "scroll",
    "tabs": lambda advanced: cycle_tabs() or "cycle_tabs",
    "apps": lambda advanced: cycle_apps() or "cycle_apps",
    "keys": _keys,
}


def _run_actions(
    stop_event: threading.Event,
    mode: str = "basic",
    enable_keys: bool = True,
    enable_typing: bool = False,
    intensity: str = Intensity.MED,
    enabled: set[str] | None = None,
    breaks: bool = True,
) -> None:
    """Without `enabled`, pick actions by mode; with it, pick uniformly from those ACTIONS names."""
    sched = _build_scheduler(intensity)
    actions: List[str] = []
    last_summary = time.time()

    for interval in sched.intervals(stop_condition=stop_event.is_set):
        if stop_event.is_set():
            break

        if interval < 0 and not breaks:
            continue
        if interval < 0:
            dur = -interval
            if dur >= 10:
                logging.info("Micro-break for %.1fs", dur)
            else:
                logging.info("Short pause for %.1fs", dur)
            waited = 0.0
            while waited < dur:
                if stop_event.wait(0.5):
                    break
                waited += 0.5
            continue

        roll = random.random()
        try:
            if enabled is not None:
                if enabled:
                    actions.append(ACTIONS[random.choice(sorted(enabled))](mode == "advanced"))
            elif mode == "advanced":
                if roll < 0.35:
                    x, y = move_cursor_safe()
                    actions.append(f"move({x},{y})")
                elif roll < 0.55:
                    scroll_safe()
                    actions.append("scroll")
                elif roll < 0.75 and enable_keys:
                    act = silent_keys() if not enable_typing else perform_safe_key_action()
                    actions.append(f"key:{act}")
                elif roll < 0.90 and enable_typing:
                    natural_typing()
                    actions.append("typing")
                else:
                    cycle_apps()
                    actions.append("cycle_apps")
            else:
                if enable_keys:
                    if roll < 0.55:
                        x, y = move_cursor_safe()
                        actions.append(f"move({x},{y})")
                    elif roll < 0.85:
                        scroll_safe()
                        actions.append("scroll")
                    else:
                        act = perform_safe_key_action()
                        actions.append(f"key:{act}")
                else:
                    if roll < 0.6:
                        x, y = move_cursor_safe()
                        actions.append(f"move({x},{y})")
                    else:
                        scroll_safe()
                        actions.append("scroll")
        except Exception as exc:
            logging.warning("Action failed: %s", exc)

        now = time.time()
        if now - last_summary >= 60.0:
            logging.info("Actions last minute: %d", len(actions))
            actions.clear()
            last_summary = now

        waited = 0.0
        while waited < interval:
            if stop_event.wait(0.5):
                break
            waited += 0.5


def _emergency_stop(stop_event: threading.Event) -> None:
    stop_event.set()
    try:
        keyboard.release("ctrl")
        keyboard.release("alt")
        keyboard.release("shift")
        keyboard.release("win")
    except Exception:
        pass
    logging.warning("Emergency stop triggered.")


def main() -> int:
    parser = argparse.ArgumentParser(description="reminder - discreet desktop activity simulator")
    parser.add_argument("--intensity", choices=[Intensity.LOW, Intensity.MED, Intensity.HIGH], default=Intensity.MED)
    parser.add_argument("--mode", choices=["basic", "advanced"], default="basic")
    parser.add_argument("--duration", type=float, default=None, help="Run for N minutes then stop")
    parser.add_argument("--no-keys", action="store_true", help="Disable keyboard actions")
    parser.add_argument("--typing", action="store_true", help="Enable natural typing in advanced mode")
    args = parser.parse_args()

    logging.info("Starting reminder | intensity=%s mode=%s", args.intensity, args.mode)

    stop_event = threading.Event()

    def handle_signal(signum, frame):  # type: ignore[no-untyped-def]
        logging.info("Signal %s received; shutting down.", signum)
        stop_event.set()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    hotkeys = HotkeyManager(
        on_start=lambda: logging.info("Hotkey start pressed"),
        on_stop=lambda: stop_event.set(),
        on_emergency=lambda: _emergency_stop(stop_event),
    )
    hotkeys.start()

    max_runtime = args.duration * 60.0 if args.duration else None
    scheduler = _build_scheduler(args.intensity)
    scheduler.max_runtime = max_runtime

    with PowerManager():
        try:
            _run_actions(
                stop_event,
                mode=args.mode,
                enable_keys=not args.no_keys,
                enable_typing=args.typing,
                intensity=args.intensity,
            )
        except Exception as exc:
            logging.error("Fatal error: %s", exc)
            hotkeys.stop()
            return 1

    hotkeys.stop()
    logging.info("Shutdown complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

