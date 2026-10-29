"""Smoke test for the desktop UI with real input actions stubbed out."""

from __future__ import annotations

import time
import tkinter as tk

import pytest

import src.main
from src.gui import App


def test_start_stop_and_validation(monkeypatch):  # type: ignore[no-untyped-def]
    monkeypatch.setattr(src.main, "move_cursor_safe", lambda: (1, 1))
    monkeypatch.setattr(src.main, "scroll_safe", lambda: None)
    key_actions = []

    def perform_key_action():  # type: ignore[no-untyped-def]
        key_actions.append("f15")
        return "f15"

    monkeypatch.setattr(src.main, "perform_safe_key_action", perform_key_action)
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    app = App(root)
    assert app.enable_key_actions.get() is True

    app.show_help()
    assert app.help_win is not None and app.help_win.winfo_exists()
    app.help_win.destroy()

    for var in app.features.values():  # nothing to do is rejected inline
        var.set(False)
    app.start()
    assert not app.running and app.error.cget("text")

    app.features["move"].set(True)
    app.features["scroll"].set(True)
    app.start()
    assert app.running and not app.error.cget("text")
    assert app.key_actions.cget("state") == "disabled"
    time.sleep(1.2)
    app.stop()
    app.worker.join(timeout=3)
    assert not app.running
    app._poll()
    assert app.key_actions.cget("state") == "normal"
    assert not key_actions
    assert "Started" in app.log.get("1.0", "end")
    app.hotkeys.stop()
    root.destroy()
