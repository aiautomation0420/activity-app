"""Key engine: safe, non-text key events and optional natural typing."""

from __future__ import annotations

import random
import time

import keyboard

# Allowed actions: no text injection.
ALLOWED_ACTIONS = [
    "alt+tab",
    "alt+esc",
    "ctrl+shift+tab",
    "ctrl+tab",
    "f5",
    "f15",
    "volume up",
    "volume down",
    "volume mute",
    "media next",
    "media prev",
    "media play pause",
    "pgup",
    "pgdn",
    "home",
    "end",
    "left",
    "right",
    "up",
    "down",
]


def perform_safe_key_action() -> str:
    """Trigger one safe key action; return what was triggered."""
    action = random.choice(ALLOWED_ACTIONS)
    keyboard.press_and_release(action)
    return action


def silent_keys() -> str:
    """Alias for perform_safe_key_action."""
    return perform_safe_key_action()


def natural_typing(
    text: str | None = None,
    min_wpm: float = 30.0,
    max_wpm: float = 90.0,
) -> str:
    """Type text character-by-character with variable WPM and pauses."""
    if text is None:
        text = random.choice(["ok", "yes", "no", "thanks", "got it"])
    for ch in text:
        if ch == " ":
            action = "space"
        else:
            action = ch
        keyboard.press_and_release(action)
        wpm = random.uniform(min_wpm, max_wpm)
        delay = 60.0 / (wpm * 5.0)
        time.sleep(random.uniform(delay * 0.7, delay * 1.3))
    return text
