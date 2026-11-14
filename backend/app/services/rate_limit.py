"""Limits for expensive routes (audit M1). Used by POST /report; Adrian can reuse it for /explain.

``RequestLimiter.slot(client_key)`` is a context manager that admits a request only when:
  * fewer than ``max_concurrent`` requests are running (else ``busy_code``, 503 by default), and
  * the client made fewer than ``max_per_window`` requests in the last ``window_s`` seconds (else
    ``RATE_LIMITED``, 429).
Both errors carry ``details.retry_after_s``, which errors.py also sends as a ``Retry-After`` header.

State lives in memory in one process (one Render instance): a restart resets it, which is fine for
abuse protection. A refused "busy" attempt does not use up the client's quota.
"""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from contextlib import contextmanager
from typing import Callable, Iterator

from ..errors import api_error

# POST /report: each PDF draws charts (CPU + memory on a 512 MB free instance).
REPORT_MAX_CONCURRENT = 2
REPORT_MAX_PER_WINDOW = 10
REPORT_WINDOW_S = 60.0
BUSY_RETRY_S = 5
BUSY_MESSAGE = "The server is busy creating other reports. Please try again in a few seconds."
RATE_MESSAGE = "Too many requests from this device. Please wait a minute and try again."


class RequestLimiter:
    def __init__(self, max_concurrent: int, max_per_window: int, window_s: float,
                 clock: Callable[[], float] = time.monotonic, busy_code: str = "REPORT_BUSY") -> None:
        if max_concurrent < 1 or max_per_window < 1 or window_s <= 0:
            raise ValueError("RequestLimiter limits must be positive")
        self._max_per_window = max_per_window
        self._window_s = float(window_s)
        self._clock = clock
        self._busy_code = busy_code
        self._slots = threading.BoundedSemaphore(max_concurrent)
        self._lock = threading.Lock()
        self._recent: dict[str, deque[float]] = {}

    def tracked_clients(self) -> int:
        with self._lock:
            return len(self._recent)

    def _forget_old(self, now: float) -> None:
        cutoff = now - self._window_s
        for key in list(self._recent):
            stamps = self._recent[key]
            while stamps and stamps[0] <= cutoff:
                stamps.popleft()
            if not stamps:
                del self._recent[key]

    def _admit(self, client_key: str) -> None:
        now = self._clock()
        with self._lock:
            self._forget_old(now)
            stamps = self._recent.setdefault(client_key, deque())
            if len(stamps) >= self._max_per_window:
                retry_after = max(1, math.ceil(stamps[0] + self._window_s - now))
                raise api_error("RATE_LIMITED", RATE_MESSAGE,
                                {"retry_after_s": retry_after, "limit": self._max_per_window,
                                 "window_s": int(self._window_s)})
            stamps.append(now)

    @contextmanager
    def slot(self, client_key: str) -> Iterator[None]:
        if not self._slots.acquire(blocking=False):
            raise api_error(self._busy_code, BUSY_MESSAGE, {"retry_after_s": BUSY_RETRY_S})
        try:
            self._admit(client_key)
            yield
        finally:
            self._slots.release()


def report_limiter() -> RequestLimiter:
    return RequestLimiter(REPORT_MAX_CONCURRENT, REPORT_MAX_PER_WINDOW, REPORT_WINDOW_S)
