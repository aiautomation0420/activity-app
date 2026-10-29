"""Power management: prevent Windows sleep/idle via ctypes."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Optional

# Windows ES_CONTINUOUS + ES_SYSTEM_REQUIRED + ES_DISPLAY_REQUIRED
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002


def prevent_sleep() -> None:
    """Tell Windows the system is in use to prevent sleep and display dimming."""
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(
            ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
        )
    except (AttributeError, OSError):
        # Non-Windows or kernel32 unavailable; ignore safely.
        pass


def restore_sleep() -> None:
    """Restore default system idle behavior."""
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
    except (AttributeError, OSError):
        pass


class PowerManager:
    """Context manager for power-state safety."""

    def __enter__(self) -> "PowerManager":
        prevent_sleep()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore[no-untyped-def]
        restore_sleep()
