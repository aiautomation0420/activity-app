"""Global hotkeys for start, stop, and emergency stop."""

from __future__ import annotations

import threading
from typing import Callable

import keyboard


class HotkeyManager:
    """Register global hotkeys for start/stop/emergency stop."""

    def __init__(self, on_start: Callable[[], None], on_stop: Callable[[], None], on_emergency: Callable[[], None]) -> None:
        self._on_start = on_start
        self._on_stop = on_stop
        self._on_emergency = on_emergency
        self._registered: list[str] = []
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        """Start listening for hotkeys in a background thread."""
        self._stop.clear()
        self._thread = threading.Thread(target=self._listen, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop listening and unhook hotkeys."""
        self._stop.set()
        try:
            keyboard.unhook_all_hotkeys()
        except Exception:
            pass
        if self._thread:
            self._thread.join(timeout=2.0)

    def _listen(self) -> None:
        try:
            keyboard.add_hotkey("ctrl+shift+space", self._on_start, suppress=False)
            self._registered.append("ctrl+shift+space")
            keyboard.add_hotkey("ctrl+shift+esc", self._on_stop, suppress=False)
            self._registered.append("ctrl+shift+esc")
            keyboard.add_hotkey("ctrl+alt+shift", self._on_emergency, suppress=False)
            self._registered.append("ctrl+alt+shift")
            while not self._stop.wait(1.0):
                pass
        except Exception:
            pass
