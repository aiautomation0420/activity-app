"""Safety tests for reminder."""

from __future__ import annotations

import threading
import types

import pytest

import src.main
from src.cursor import MAX_DELTA, MIN_DELTA, SCROLL_MAX, SCROLL_MIN, SafeClickZone, click_in_place, move_cursor_safe
from src.exclusions import EXCLUDE_TITLES, _is_excluded
from src.hotkeys import HotkeyManager
from src.keys import ALLOWED_ACTIONS, natural_typing, perform_safe_key_action
from src.power import PowerManager, prevent_sleep, restore_sleep
from src.scheduler import Intensity, Scheduler


# ----- Power -----


class DummyKernel32:
    state = 0

    @staticmethod
    def SetThreadExecutionState(flags):  # type: ignore[no-untyped-def]
        DummyKernel32.state = flags


def _fake_windll(monkeypatch):  # type: ignore[no-untyped-def]
    fake = types.SimpleNamespace(kernel32=DummyKernel32())
    monkeypatch.setattr("ctypes.windll", fake, raising=False)
    DummyKernel32.state = 0


def test_prevent_sleep_sets_flags(monkeypatch):  # type: ignore[no-untyped-def]
    _fake_windll(monkeypatch)
    prevent_sleep()
    assert DummyKernel32.state != 0


def test_restore_sleep_clears_flags(monkeypatch):  # type: ignore[no-untyped-def]
    from src.power import ES_CONTINUOUS
    _fake_windll(monkeypatch)
    restore_sleep()
    assert DummyKernel32.state == ES_CONTINUOUS


def test_power_manager_context(monkeypatch):  # type: ignore[no-untyped-def]
    from src.power import ES_CONTINUOUS
    _fake_windll(monkeypatch)
    with PowerManager():
        assert DummyKernel32.state != 0
    assert DummyKernel32.state == ES_CONTINUOUS


# ----- Scheduler -----


def test_scheduler_invalid_args() -> None:
    with pytest.raises(ValueError):
        Scheduler(min_delay=-1, max_delay=1)
    with pytest.raises(ValueError):
        Scheduler(micro_break_every=0)
    with pytest.raises(ValueError):
        Scheduler(short_pause_every=0)


def test_scheduler_produces_intervals() -> None:
    s = Scheduler(min_delay=0.5, max_delay=1.0, micro_break_every=9999.0, micro_break_duration=1.0, short_pause_every=9999.0, short_pause_duration=(1.0, 1.0))
    it = s.intervals()
    val = next(it)
    assert 0.5 <= val <= 1.0


def test_scheduler_micro_break_sentinel() -> None:
    s = Scheduler(min_delay=0.1, max_delay=0.2, micro_break_every=0.1, micro_break_duration=1.0, short_pause_every=9999.0, short_pause_duration=(1.0, 1.0))
    s._next_break = 0.0
    vals = []
    for v in s.intervals():
        vals.append(v)
        if len(vals) >= 2:
            break
    assert any(v < 0 for v in vals)


def test_scheduler_short_pause_sentinel() -> None:
    s = Scheduler(min_delay=0.1, max_delay=0.2, micro_break_every=9999.0, micro_break_duration=1.0, short_pause_every=0.1, short_pause_duration=(1.0, 1.0))
    s._next_short_pause = 0.0
    vals = []
    for v in s.intervals():
        vals.append(v)
        if len(vals) >= 2:
            break
    assert any(v < 0 for v in vals)


def test_intensity_adaptation() -> None:
    low = Scheduler(Intensity.LOW, min_delay=2.0, max_delay=8.0, micro_break_every=9999.0, micro_break_duration=1.0, short_pause_every=9999.0, short_pause_duration=(1.0, 1.0))
    high = Scheduler(Intensity.HIGH, min_delay=2.0, max_delay=8.0, micro_break_every=9999.0, micro_break_duration=1.0, short_pause_every=9999.0, short_pause_duration=(1.0, 1.0))
    lo, hi = low._adapt()
    assert lo >= 1.0
    assert hi <= 12.0
    lo2, hi2 = high._adapt()
    assert lo2 <= 2.0
    assert hi2 <= 6.0


# ----- Cursor safety -----


def test_delta_limits() -> None:
    assert MIN_DELTA >= 1
    assert MAX_DELTA <= 200
    assert SCROLL_MIN >= 1
    assert SCROLL_MAX <= 10


def test_safe_click_zone() -> None:
    zone = SafeClickZone(10, 20, 30, 40)
    assert zone.contains(10, 20)
    assert zone.contains(30, 40)
    assert not zone.contains(5, 20)
    assert not zone.contains(10, 50)


def test_click_in_place_returns_coords(monkeypatch):  # type: ignore[no-untyped-def]
    import src.cursor as cursor
    clicks = []

    def fake_click(x, y):  # type: ignore[no-untyped-def]
        clicks.append((x, y))

    monkeypatch.setattr(cursor.pyautogui, "click", fake_click)
    x, y = click_in_place(SafeClickZone(0, 0, 10, 10))
    assert 0 <= x <= 10
    assert 0 <= y <= 10
    assert clicks == [(x, y)]


# ----- Keys safety -----


def test_no_text_injection() -> None:
    for action in ALLOWED_ACTIONS:
        assert "+" in action or action.startswith("f") or "volume" in action or "media" in action or action in {"pgup", "pgdn", "home", "end", "left", "right", "up", "down"}
        assert action.lower() not in {"a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l", "m"}


def test_allowed_actions_non_empty() -> None:
    assert len(ALLOWED_ACTIONS) > 0


def test_perform_safe_key_action_returns_string(monkeypatch):  # type: ignore[no-untyped-def]
    import src.keys as keys

    called = {"v": None}

    def fake_press_and_release(action):  # type: ignore[no-untyped-def]
        called["v"] = action

    monkeypatch.setattr(keys.keyboard, "press_and_release", fake_press_and_release)
    result = perform_safe_key_action()
    assert result == called["v"]
    assert result in ALLOWED_ACTIONS


def test_natural_typing_presses_chars(monkeypatch):  # type: ignore[no-untyped-def]
    import src.keys as keys

    pressed = []

    def fake_press_and_release(action):  # type: ignore[no-untyped-def]
        pressed.append(action)

    monkeypatch.setattr(keys.keyboard, "press_and_release", fake_press_and_release)
    monkeypatch.setattr(keys.time, "sleep", lambda _: None)
    result = natural_typing("ok", min_wpm=60.0, max_wpm=60.0)
    assert result == "ok"
    assert "o" in pressed
    assert "k" in pressed


def test_run_actions_skips_key_actions_when_disabled(monkeypatch):  # type: ignore[no-untyped-def]
    stop_event = threading.Event()
    calls = {"scroll": 0, "key": 0}

    class OneInterval:
        def intervals(self, stop_condition=None):  # type: ignore[no-untyped-def]
            yield 0.1

    def scroll():  # type: ignore[no-untyped-def]
        calls["scroll"] += 1
        stop_event.set()

    def key_action():  # type: ignore[no-untyped-def]
        calls["key"] += 1
        return "f15"

    monkeypatch.setattr(src.main, "_build_scheduler", lambda intensity: OneInterval())
    monkeypatch.setattr(src.main.random, "random", lambda: 0.9)
    monkeypatch.setattr(src.main, "scroll_safe", scroll)
    monkeypatch.setattr(src.main, "perform_safe_key_action", key_action)

    src.main._run_actions(stop_event, mode="basic", enable_keys=False)

    assert calls == {"scroll": 1, "key": 0}


def test_run_actions_only_runs_enabled_and_skips_breaks(monkeypatch):  # type: ignore[no-untyped-def]
    stop_event = threading.Event()
    calls = []

    class BreakThenAction:
        def intervals(self, stop_condition=None):  # type: ignore[no-untyped-def]
            yield -60.0  # would wait a minute if breaks were on
            yield 0.1

    def scroll():  # type: ignore[no-untyped-def]
        calls.append("scroll")
        stop_event.set()

    monkeypatch.setattr(src.main, "_build_scheduler", lambda intensity: BreakThenAction())
    monkeypatch.setattr(src.main, "scroll_safe", scroll)
    monkeypatch.setattr(src.main, "move_cursor_safe", lambda: calls.append("move") or (0, 0))

    src.main._run_actions(stop_event, enabled={"scroll"}, breaks=False)

    assert calls == ["scroll"]


# ----- Exclusions -----


def test_is_excluded(monkeypatch):  # type: ignore[no-untyped-def]
    monkeypatch.setattr("src.exclusions._active_window_title", lambda: "chrome")
    assert _is_excluded() is False
    monkeypatch.setattr("src.exclusions._active_window_title", lambda: "reminder")
    assert _is_excluded() is True
    monkeypatch.setattr("src.exclusions._active_window_title", lambda: "reminders")
    assert _is_excluded() is True
    monkeypatch.setattr("src.exclusions._active_window_title", lambda: "explorer")
    assert _is_excluded() is False


# ----- Hotkeys -----


def test_hotkey_manager_lifecycle() -> None:
    started = []
    stopped = []
    emergency_called = []

    def on_start():  # type: ignore[no-untyped-def]
        started.append(True)

    def on_stop():  # type: ignore[no-untyped-def]
        stopped.append(True)

    def on_emergency():  # type: ignore[no-untyped-def]
        emergency_called.append(True)

    mgr = HotkeyManager(on_start, on_stop, on_emergency)
    mgr.start()
    assert mgr._thread is not None
    mgr.stop()
    assert not mgr._thread.is_alive()
