"""App/tab cycling with self-exclusion."""

from __future__ import annotations

import random

import pyautogui

EXCLUDE_TITLES = {"reminder", "reminders"}


def _active_window_title() -> str:
    try:
        import win32gui  # type: ignore[import-untyped]
        return win32gui.GetWindowText(win32gui.GetForegroundWindow()).lower()
    except Exception:
        return ""


def _is_excluded() -> bool:
    title = _active_window_title()
    return any(excluded in title for excluded in EXCLUDE_TITLES)


def cycle_apps() -> None:
    """Alt+tab to the next app, skipping excluded windows."""
    if _is_excluded():
        return
    pyautogui.hotkey("alt", "tab")


def cycle_tabs() -> None:
    """Ctrl+tab to the next browser tab, skipping excluded windows."""
    if _is_excluded():
        return
    pyautogui.hotkey("ctrl", "tab")
