"""Cursor movement: mouse move, scroll, and safe click zones."""

from __future__ import annotations

import random
from typing import Tuple

import pyautogui

# Safety caps
MAX_DELTA = 120
MIN_DELTA = 3
SCROLL_MIN = 1
SCROLL_MAX = 3


def _clamp_delta(value: int) -> int:
    return max(MIN_DELTA, min(MAX_DELTA, int(value)))


def move_cursor_safe() -> Tuple[int, int]:
    """Move cursor by a small randomized delta; return new absolute position."""
    screen_w, screen_h = pyautogui.size()
    cur_x, cur_y = pyautogui.position()

    dx = _clamp_delta(random.randint(-MAX_DELTA, MAX_DELTA))
    dy = _clamp_delta(random.randint(-MAX_DELTA, MAX_DELTA))

    new_x = max(0, min(screen_w - 1, cur_x + dx))
    new_y = max(0, min(screen_h - 1, cur_y + dy))

    pyautogui.moveTo(new_x, new_y, duration=random.uniform(0.1, 0.3))
    return new_x, new_y


def scroll_safe() -> None:
    """Perform a small randomized scroll step."""
    steps = random.randint(SCROLL_MIN, SCROLL_MAX)
    pyautogui.scroll(steps)


class SafeClickZone:
    """Rectangular click allowlist."""

    def __init__(self, x1: int, y1: int, x2: int, y2: int) -> None:
        self.x1 = min(x1, x2)
        self.y1 = min(y1, y2)
        self.x2 = max(x1, x2)
        self.y2 = max(y1, y2)

    def contains(self, x: int, y: int) -> bool:
        return self.x1 <= x <= self.x2 and self.y1 <= y <= self.y2


DEFAULT_ZONES = [
    SafeClickZone(0, 0, 100, 40),  # title bar area
    SafeClickZone(0, 0, 200, 1000),  # sidebar-ish
]


def click_in_place(zone: SafeClickZone | None = None) -> Tuple[int, int]:
    """Click within a safe zone, or a random default zone if none provided."""
    z = zone or random.choice(DEFAULT_ZONES)
    x = random.randint(z.x1, z.x2)
    y = random.randint(z.y1, z.y2)
    pyautogui.click(x, y)
    return x, y
