"""Latest-frame buffer for an Operator browser camera feeding the detector."""
from __future__ import annotations

import threading
import time

import numpy as np


class BrowserCamera:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._frame: np.ndarray | None = None
        self._sequence = 0
        self._received_at = 0.0
        self._fps = 0.0
        self._fps_count = 0
        self._fps_started = time.monotonic()

    def submit(self, frame: np.ndarray) -> int:
        now = time.monotonic()
        with self._lock:
            self._frame = frame.copy()
            self._sequence += 1
            self._received_at = now
            self._fps_count += 1
            elapsed = now - self._fps_started
            if elapsed >= 1.0:
                self._fps = self._fps_count / elapsed
                self._fps_count = 0
                self._fps_started = now
            return self._sequence

    def get_newer_than(self, sequence: int, max_age: float = 1.0):
        with self._lock:
            if self._frame is None or self._sequence <= sequence:
                return None
            if time.monotonic() - self._received_at > max_age:
                return None
            return self._frame.copy(), self._sequence

    @property
    def is_available(self) -> bool:
        with self._lock:
            return self._frame is not None and time.monotonic() - self._received_at <= 1.0

    @property
    def fps(self) -> float:
        with self._lock:
            if self._frame is None or time.monotonic() - self._received_at > 1.0:
                return 0.0
            return round(self._fps, 1)


browser_camera = BrowserCamera()
