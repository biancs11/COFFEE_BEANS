"""
Raspberry Pi Camera — production-hardened with reconnect circuit breaker.

Changes from dev version:
  • Consecutive-failure counter → triggers reconnect after N failures
  • Full reinitialise on picamera2 AND OpenCV disconnect
  • Exponential back-off between reconnect attempts (cap 60 s)
  • CameraState enum so callers (websocket, health endpoint) can read status
  • All dimensions / FPS driven by config.settings
  • get_jpeg() JPEG quality param exposed; returns None gracefully
"""

from __future__ import annotations

import logging
import threading
import time
import os
from enum import Enum

import cv2
import numpy as np

# Suppress noisy FFmpeg/OpenCV MJPEG decoder warnings
os.environ.setdefault("OPENCV_VIDEOIO_DEBUG", "0")
os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")

from backend.core.config import settings

logger = logging.getLogger(__name__)

try:
    from picamera2 import Picamera2
    PICAMERA_AVAILABLE = True
    logger.info("picamera2 detected — using Raspberry Pi Camera")
except ImportError:
    PICAMERA_AVAILABLE = False
    logger.warning("picamera2 not found — falling back to OpenCV VideoCapture")


# ── Camera state machine ────────────────────────────────────────────────────

class CameraState(str, Enum):
    STOPPED      = "stopped"
    STARTING     = "starting"
    RUNNING      = "running"
    RECONNECTING = "reconnecting"
    ERROR        = "error"


# ══════════════════════════════════════════════════════════════════════════
# CameraManager
# ══════════════════════════════════════════════════════════════════════════

class CameraManager:
    """
    Thread-safe camera wrapper for Raspberry Pi (picamera2) with
    automatic fallback to OpenCV VideoCapture and full reconnect logic.

    State machine:
        STOPPED → STARTING → RUNNING ⟵→ RECONNECTING → ERROR
    """

    # Consecutive failures before triggering a reconnect attempt
    _FAILURE_THRESHOLD: int = settings.CAMERA_MAX_FAILURES

    def __init__(self):
        self._lock          = threading.Lock()
        self._frame:  np.ndarray | None = None
        self._state         = CameraState.STOPPED
        self._thread: threading.Thread | None = None

        # Metrics
        self._fps_actual     = 0.0
        self._frame_count    = 0
        self._fps_timer      = time.time()
        self._consecutive_failures = 0
        self._total_frames   = 0
        self._reconnect_count= 0
        self._last_error: str= ""

        # Hardware handles
        self._picam = None
        self._cap:   cv2.VideoCapture | None = None
        self._ip_stream_source: str | None = None
        self._ip_stream_bytes  = b""

    # ── Public lifecycle ────────────────────────────────────────────────

    def start(self) -> None:
        if self._state not in (CameraState.STOPPED, CameraState.ERROR):
            logger.debug("Camera already running / starting — ignoring start()")
            return
        self._state   = CameraState.STARTING
        self._thread  = threading.Thread(
            target=self._run_loop, daemon=True, name="camera-loop"
        )
        self._thread.start()
        logger.info("Camera thread started")

    def stop(self) -> None:
        logger.info("Stopping camera …")
        self._state = CameraState.STOPPED
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=4)
        self._release()
        logger.info("Camera stopped")

    # ── Properties ──────────────────────────────────────────────────────

    @property
    def fps(self) -> float:
        return round(self._fps_actual, 1)

    @property
    def state(self) -> CameraState:
        return self._state

    @property
    def is_running(self) -> bool:
        return self._state == CameraState.RUNNING

    @property
    def stats(self) -> dict:
        return {
            "state":           self._state.value,
            "fps":             self.fps,
            "total_frames":    self._total_frames,
            "reconnect_count": self._reconnect_count,
            "last_error":      self._last_error,
            "consecutive_failures": self._consecutive_failures,
        }

    # ── Frame access ────────────────────────────────────────────────────

    def get_frame(self) -> np.ndarray | None:
        with self._lock:
            return self._frame.copy() if self._frame is not None else None

    def get_jpeg(self, quality: int = 82) -> bytes | None:
        frame = self.get_frame()
        if frame is None:
            return None
        ok, buf = cv2.imencode(
            ".jpg", frame,
            [cv2.IMWRITE_JPEG_QUALITY, quality]
        )
        return bytes(buf) if ok else None

    # ── Main capture loop ────────────────────────────────────────────────

    def _run_loop(self) -> None:
        """
        Outer loop: handles initialise → capture → reconnect cycle.
        Runs in a daemon thread for the lifetime of the process.
        """
        backoff = settings.CAMERA_RECONNECT_DELAY   # seconds, doubles on failure

        while self._state != CameraState.STOPPED:

            # ── Initialise hardware ────────────────────────────────────
            try:
                self._initialise()
                self._state              = CameraState.RUNNING
                self._consecutive_failures = 0
                backoff                  = settings.CAMERA_RECONNECT_DELAY
                logger.info("Camera initialised — entering capture loop")
            except Exception as exc:
                self._last_error = str(exc)
                logger.error(f"Camera init failed: {exc}")
                self._state = CameraState.RECONNECTING
                self._release()
                self._sleep_backoff(backoff)
                backoff = min(backoff * 2, 60)
                continue

            # ── Inner capture loop ─────────────────────────────────────
            while self._state == CameraState.RUNNING:
                try:
                    frame = self._read_frame()
                    if frame is None:
                        self._on_failure("read_frame returned None")
                        continue

                    frame = self._preprocess(frame)

                    with self._lock:
                        self._frame = frame

                    self._consecutive_failures = 0
                    self._total_frames        += 1
                    self._update_fps()

                except Exception as exc:
                    self._on_failure(str(exc))

            # If we exit the inner loop due to too many failures, reconnect
            if self._state == CameraState.RECONNECTING:
                logger.warning(
                    f"Camera reconnecting (attempt #{self._reconnect_count + 1}) "
                    f"after {self._consecutive_failures} consecutive failures"
                )
                self._reconnect_count += 1
                self._release()
                self._sleep_backoff(backoff)
                backoff = min(backoff * 2, 60)

        # Ensure hardware is released when stopped
        self._release()

    def _on_failure(self, reason: str) -> None:
        self._consecutive_failures += 1
        self._last_error = reason

        # IP Webcam over HTTP — give it more retries before reconnecting
        # because a single slow/dropped HTTP request is normal
        source    = settings.CAMERA_SOURCE.strip()
        threshold = 15 if source else self._FAILURE_THRESHOLD

        if self._consecutive_failures == 1:
            logger.warning(f"Camera read failure: {reason}")
        elif self._consecutive_failures % 5 == 0:
            logger.error(
                f"Camera: {self._consecutive_failures} consecutive failures — {reason}"
            )

        if self._consecutive_failures >= threshold:
            logger.error(
                f"Camera failure threshold ({threshold}) reached — triggering reconnect"
            )
            self._state = CameraState.RECONNECTING
        else:
            time.sleep(0.1)

    def _sleep_backoff(self, seconds: float) -> None:
        """Interruptible sleep — checks STOPPED state every 0.5 s."""
        elapsed = 0.0
        while elapsed < seconds and self._state != CameraState.STOPPED:
            time.sleep(0.5)
            elapsed += 0.5

    # ── Hardware init / release ─────────────────────────────────────────

    def _initialise(self) -> None:
        if PICAMERA_AVAILABLE:
            self._init_picam()
        else:
            self._init_opencv()

    def _init_picam(self) -> None:
        if self._picam:
            try:
                self._picam.stop()
                self._picam.close()
            except Exception:
                pass
            self._picam = None

        self._picam = Picamera2()
        config = self._picam.create_video_configuration(
            main={
                "size":   (settings.CAMERA_WIDTH, settings.CAMERA_HEIGHT),
                "format": "RGB888",
            },
            controls={
                "FrameDurationLimits": (
                    int(1_000_000 / settings.CAMERA_FPS),
                    int(1_000_000 / settings.CAMERA_FPS),
                ),
                "ExposureTime":    10_000,
                "AnalogueGain":    1.0,
                "AwbEnable":       True,
                "AeEnable":        True,
                "NoiseReductionMode": 1,
                "Sharpness":       1.5,
            },
        )
        self._picam.configure(config)
        self._picam.start()
        time.sleep(1.0)   # warm-up

    def _init_opencv(self) -> None:
        if self._cap:
            self._cap.release()
            self._cap = None

        source = settings.CAMERA_SOURCE.strip()
        if source:
            # For IP Webcam MJPEG streams, OpenCV routes via FFmpeg which
            # tries TCP and fails. We use urllib to fetch frames directly.
            # Test the URL is reachable before marking as opened.
            import urllib.request
            try:
                req = urllib.request.urlopen(source, timeout=5)
                req.close()
            except Exception as exc:
                raise RuntimeError(
                    f"Cannot reach IP Webcam at {source}: {exc}\n"
                    "Ensure the IP Webcam app is running and phone is on same Wi-Fi."
                )
            # Store source — _read_frame will fetch via urllib
            self._ip_stream_source = source
            self._cap = None   # not used for IP streams
            logger.info(f"IP Webcam source confirmed reachable: {source}")
            return

        self._ip_stream_source = None

        # Local camera — scan indices 0..35 to support Raspberry Pi CSI cameras
        # on Debian Trixie / Pi OS Bookworm where the CSI camera shows up at
        # higher indices (e.g. /dev/video23) instead of /dev/video0.
        # We skip metadata-only V4L2 sub-devices by verifying a frame can be read.
        tried = []
        for idx in list(range(0, 36)):
            try:
                cap = cv2.VideoCapture(idx)
                if not cap.isOpened():
                    cap.release()
                    continue
                # Verify the device actually produces frames (skip meta devices)
                ret, frame = cap.read()
                if not ret or frame is None:
                    cap.release()
                    continue
                cap.set(cv2.CAP_PROP_FRAME_WIDTH,  settings.CAMERA_WIDTH)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, settings.CAMERA_HEIGHT)
                cap.set(cv2.CAP_PROP_FPS,           settings.CAMERA_FPS)
                cap.set(cv2.CAP_PROP_BUFFERSIZE,    1)
                self._cap = cap
                logger.info(f"Camera opened at index {idx} (/dev/video{idx})")
                return
            except Exception as exc:
                tried.append(idx)
                logger.debug(f"Camera index {idx} failed: {exc}")
                continue
        raise RuntimeError(f"No camera device found at indices 0-35. Tried: {tried}")

    def _release(self) -> None:
        if PICAMERA_AVAILABLE and self._picam:
            try:
                self._picam.stop()
                self._picam.close()
            except Exception:
                pass
            self._picam = None

        if self._cap:
            self._cap.release()
            self._cap = None

        self._ip_stream_source = None
        self._ip_stream_bytes  = b""

        with self._lock:
            self._frame = None

    # ── Frame read ──────────────────────────────────────────────────────

    def _read_frame(self) -> np.ndarray | None:
        if PICAMERA_AVAILABLE:
            rgb = self._picam.capture_array()
            return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

        # IP Webcam — fetch a single snapshot via HTTP (avoids FFmpeg TCP issue)
        if self._ip_stream_source:
            return self._read_ip_frame()

        # Local USB camera
        if self._cap is None:
            return None
        for _ in range(4):
            self._cap.grab()
        ret, frame = self._cap.retrieve()
        return frame if ret else None

    def _read_ip_frame(self) -> np.ndarray | None:
        """
        Fetch one JPEG snapshot from IP Webcam using urllib /shot.jpg.
        Retries once on timeout so a single slow response doesn't count
        as a camera failure.
        """
        import urllib.request
        import urllib.error

        base = self._ip_stream_source.rstrip('/')
        if base.endswith('/video'):
            snapshot_url = base[:-6] + '/shot.jpg'
        elif base.endswith('/videofeed'):
            snapshot_url = base[:-10] + '/shot.jpg'
        else:
            snapshot_url = base.split('?')[0].rstrip('/') + '/shot.jpg'

        for attempt in range(2):   # retry once on failure
            try:
                with urllib.request.urlopen(snapshot_url, timeout=3) as resp:
                    data = resp.read()
                if not data:
                    continue
                arr   = np.frombuffer(data, dtype=np.uint8)
                frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if frame is not None:
                    return frame
            except Exception as exc:
                if attempt == 0:
                    logger.debug(f"IP frame fetch attempt {attempt+1} failed: {exc}, retrying…")
                    time.sleep(0.1)
                else:
                    logger.debug(f"IP frame fetch failed after retry: {exc}")
        return None

    # ── Pre-processing ──────────────────────────────────────────────────

    def _preprocess(self, frame: np.ndarray) -> np.ndarray:
        """
        Lightweight resize only for IP Webcam streams (phones send high-res).
        CLAHE/sharpening skipped on network streams — too slow and adds latency.
        """
        source = settings.CAMERA_SOURCE.strip()
        if source:
            # Resize to target resolution — phone cameras default to 1080p+
            h, w = frame.shape[:2]
            tw, th = settings.CAMERA_WIDTH, settings.CAMERA_HEIGHT
            if w != tw or h != th:
                frame = cv2.resize(frame, (tw, th), interpolation=cv2.INTER_LINEAR)
            return frame

        # Local camera: CLAHE contrast + mild sharpening
        lab       = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        l, a, b   = cv2.split(lab)
        clahe     = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l         = clahe.apply(l)
        frame     = cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)
        blur      = cv2.GaussianBlur(frame, (0, 0), 3)
        frame     = cv2.addWeighted(frame, 1.4, blur, -0.4, 0)
        return frame

    # ── FPS tracking ────────────────────────────────────────────────────

    def _update_fps(self) -> None:
        self._frame_count += 1
        elapsed = time.time() - self._fps_timer
        if elapsed >= 1.0:
            self._fps_actual  = self._frame_count / elapsed
            self._frame_count = 0
            self._fps_timer   = time.time()


# ── Singleton ───────────────────────────────────────────────────────────────
camera_manager = CameraManager()
