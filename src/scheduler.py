"""Scheduler: randomized intervals with adaptive rhythms, micro-breaks, and short pauses."""

from __future__ import annotations

import random
import time
from typing import Callable, Iterator, Optional


class Intensity:
    LOW = "low"
    MED = "med"
    HIGH = "high"


class Scheduler:
    """Yield randomized intervals and enforce breaks.

    - Base loop sleeps for a random duration in [min_delay, max_delay].
    - Every micro_break_every seconds, a longer micro-break pause occurs.
    - Every short_pause_every seconds, a short pause occurs.
    - Intensity mode adjusts the base delay range.
    - Optional max_runtime caps total execution time in seconds.
    """

    def __init__(
        self,
        intensity: str = Intensity.MED,
        min_delay: float = 2.0,
        max_delay: float = 8.0,
        micro_break_every: float = 600.0,
        micro_break_duration: float = 45.0,
        short_pause_every: float = 120.0,
        short_pause_duration: tuple[float, float] = (30.0, 120.0),
        max_runtime: Optional[float] = None,
    ) -> None:
        if min_delay <= 0 or max_delay < min_delay:
            raise ValueError("Invalid delay bounds.")
        if micro_break_every <= 0 or micro_break_duration <= 0:
            raise ValueError("Invalid micro-break configuration.")
        if short_pause_every <= 0 or short_pause_duration[0] < 0 or short_pause_duration[1] < short_pause_duration[0]:
            raise ValueError("Invalid short-pause configuration.")

        self.intensity = intensity
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.micro_break_every = micro_break_every
        self.micro_break_duration = micro_break_duration
        self.short_pause_every = short_pause_every
        self.short_pause_duration = short_pause_duration
        self.max_runtime = max_runtime
        self._start = time.time()
        self._next_break = time.time() + random.uniform(
            micro_break_every * 0.5, micro_break_every * 1.0
        )
        self._next_short_pause = time.time() + random.uniform(
            short_pause_every * 0.5, short_pause_every * 1.0
        )

    def _adapt(self) -> tuple[float, float]:
        if self.intensity == Intensity.LOW:
            return max(1.0, self.min_delay), min(12.0, self.max_delay * 1.5)
        if self.intensity == Intensity.HIGH:
            return max(0.5, self.min_delay * 0.7), min(6.0, self.max_delay * 0.7)
        return self.min_delay, self.max_delay

    def intervals(self, stop_condition: Optional[Callable[[], bool]] = None) -> Iterator[float]:
        """Yield sleep durations until stopped."""
        while True:
            if stop_condition and stop_condition():
                return
            if self.max_runtime is not None and (time.time() - self._start) >= self.max_runtime:
                return

            now = time.time()
            if now >= self._next_break:
                yield -self.micro_break_duration  # sentinel for micro-break
                self._next_break = now + random.uniform(
                    self.micro_break_every * 0.8, self.micro_break_every * 1.2
                )
                continue

            if now >= self._next_short_pause:
                dur = random.uniform(*self.short_pause_duration)
                yield -dur  # sentinel for short pause
                self._next_short_pause = now + random.uniform(
                    self.short_pause_every * 0.8, self.short_pause_every * 1.2
                )
                continue

            lo, hi = self._adapt()
            yield random.uniform(lo, hi)
