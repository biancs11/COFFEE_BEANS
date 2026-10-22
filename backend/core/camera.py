"""
Raspberry Pi Camera - HD 1080p, true colour, real-time.

Optimised for Raspberry Pi 5 + Camera Module 3 (imx708):
  - 1920x1080 Full HD
  - True colour: no over-saturation, no artificial processing
  - Real-time: 2-frame buffer, minimal latency
  - Full auto-exposure / auto-white-balance
  - picamera2 primary, OpenCV fallback
"""

from __future__ import annotations

import logging
import threading
import time
import os
from enum import Enum

import cv2
import numpy as np

os.environ.setdefault("OPENCV_VIDEOIO_DEBUG", "0")
os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")

from backend.core.config import settings

logger = logging.getLogger(__name__)

try:
    from picamera2 import Picamera2
    PICAMERA_AVAILABLE = True
    logger.info("picamera2 detected - using Raspberry Pi Camera Module")
except ImportError:
    PICAMERA_AVAILABLE = False
    logger.warning("picamera2 not found - falling back to OpenCV VideoCapture")


class CameraState(str, Enum):
    STOPPED      = "stopped"
    STARTING     = "starting"
    RUNNING      = "running"
    RECONNECTING = "reconnecting"
    ERROR        = "error"


class CameraManager:
    """
    Thread-safe HD camera wrapper.
    Provides true-colour 1080p frames with minimal latency.
    """

    _FAILURE_THRESHOLD: int = settings.CAMERA_MAX_FAILURES

    def __init__(self):
        self._lock                     = threading.Lock()
        self._frame: np.ndarray | None = None
        self._state                    = CameraState.STOPPED
        self._thread: threading.Thread | None = None

        self._fps_actual           = 0.0
        self._frame_count          = 0
        self._fps_timer            = time.time()
        self._consecutive_failures = 0
        self._total_frames         = 0
        self._reconnect_count      = 0
        self._last_error: str      = ""

        self._picam                              = None
        self._cap: cv2.VideoCapture | None       = None
        self._ip_stream_source: str | None       = None
        self._ip_stream_bytes                    = b""

        self._frame_interval = 1.0 / max(settings.CAMERA_FPS, 1)

    # ── Public lifecycle ─────────────────────────────────────

    def start(self) -> None:
        if self._state not in (CameraState.STOPPED, CameraState.ERROR):
            return
        self._state  = CameraState.STARTING
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="camera-loop"
        )
        self._thread.start()
        logger.info("Camera thread started")

    def stop(self) -> None:
        logger.info("Stopping camera...")
        self._state = CameraState.STOPPED
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=4)
        self._release()
        logger.info("Camera stopped")

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
            "state":                self._state.value,
            "fps":                  self.fps,
            "total_frames":         self._total_frames,
            "reconnect_count":      self._reconnect_count,
            "last_error":           self._last_error,
            "consecutive_failures": self._consecutive_failures,
        }

    def get_frame(self) -> np.ndarray | None:
        with self._lock:
            return self._frame.copy() if self._frame is not None else None

    def get_jpeg(self, quality: int = 85) -> bytes | None:
        frame = self.get_frame()
        if frame is None:
            return None
        ok, buf = cv2.imencode(
            ".jpg", frame,
            [cv2.IMWRITE_JPEG_QUALITY, quality]
        )
        return bytes(buf) if ok else None

    # ── Capture loop ─────────────────────────────────────────

    def _run_loop(self) -> None:
        backoff = settings.CAMERA_RECONNECT_DELAY

        while self._state != CameraState.STOPPED:
            try:
                self._initialise()
                self._state                = CameraState.RUNNING
                self._consecutive_failures = 0
                backoff                    = settings.CAMERA_RECONNECT_DELAY
                logger.info("Camera initialised - entering capture loop")
            except Exception as exc:
                self._last_error = str(exc)
                logger.error(f"Camera init failed: {exc}")
                self._state = CameraState.RECONNECTING
                self._release()
                self._sleep_backoff(backoff)
                backoff = min(backoff * 2, 60)
                continue

            next_frame_time = time.time()

            while self._state == CameraState.RUNNING:
                now        = time.time()
                sleep_time = next_frame_time - now
                if sleep_time > 0:
                    time.sleep(sleep_time)
                next_frame_time = time.time() + self._frame_interval

                try:
                    frame = self._read_frame()
                    if frame is None:
                        self._on_failure("read_frame returned None")
                        continue

                    with self._lock:
                        self._frame = frame

                    self._consecutive_failures = 0
                    self._total_frames        += 1
                    self._update_fps()

                except Exception as exc:
                    self._on_failure(str(exc))

            if self._state == CameraState.RECONNECTING:
                logger.warning(f"Camera reconnecting (attempt #{self._reconnect_count + 1})")
                self._reconnect_count += 1
                self._release()
                self._sleep_backoff(backoff)
                backoff = min(backoff * 2, 60)

        self._release()

    def _on_failure(self, reason: str) -> None:
        self._consecutive_failures += 1
        self._last_error = reason

        source    = settings.CAMERA_SOURCE.strip()
        threshold = 15 if source else self._FAILURE_THRESHOLD

        if self._consecutive_failures == 1:
            logger.warning(f"Camera read failure: {reason}")
        elif self._consecutive_failures % 5 == 0:
            logger.error(f"Camera: {self._consecutive_failures} consecutive failures - {reason}")

        if self._consecutive_failures >= threshold:
            self._state = CameraState.RECONNECTING
        else:
            time.sleep(0.05)

    def _sleep_backoff(self, seconds: float) -> None:
        elapsed = 0.0
        while elapsed < seconds and self._state != CameraState.STOPPED:
            time.sleep(0.5)
            elapsed += 0.5

    # ── Hardware init ─────────────────────────────────────────

    def _initialise(self) -> None:
        if PICAMERA_AVAILABLE:
            self._init_picam()
        else:
            self._init_opencv()

    def _init_picam(self) -> None:
        """
        Initialise Camera Module 3 (imx708) for HD true-colour output.

        Key settings:
        - RGB888 format captured and immediately converted to BGR for OpenCV
        - NO preprocessing — colours come directly from the ISP
        - Auto-exposure and auto-white-balance fully enabled
        - buffer_count=2 for minimum latency (always freshest frame)
        - AfMode=2 (continuous autofocus) for sharp beans at any distance
        """
        if self._picam:
            try:
                self._picam.stop()
                self._picam.close()
            except Exception:
                pass
            self._picam = None

        self._picam = Picamera2()

        # 1920x1080 HD — imx708 native support
        capture_w = min(settings.CAMERA_WIDTH,  1920)
        capture_h = min(settings.CAMERA_HEIGHT, 1080)

        config = self._picam.create_video_configuration(
            main={
                "size":   (capture_w, capture_h),
                "format": "RGB888",
            },
            controls={
                # Fast AE: min 16ms (62fps), max 50ms (20fps) — keeps reaction time fast
                "FrameDurationLimits": (16_666, 50_000),

                # Full auto — let the ISP handle colour accuracy
                "AeEnable":            True,
                "AwbEnable":           True,
                "AeMeteringMode":      0,    # centre-weighted metering
                "AeExposureMode":      0,    # normal exposure mode

                # Continuous autofocus — always sharp, no manual focus needed
                # AfMode: 0=manual, 1=auto, 2=continuous
                "AfMode":              2,
                "AfSpeed":             1,    # 0=normal, 1=fast

                # Colour: use camera defaults — no artificial boosting
                # This gives TRUE colours matching the actual bean colour
                "NoiseReductionMode":  2,    # fast noise reduction
                "Sharpness":           1.5,  # slight sharpening only
                "Contrast":            1.0,  # neutral — no change
                "Saturation":          1.0,  # neutral — true colours
                "Brightness":          0.0,  # neutral — AE handles it
            },
            # 2 frame buffers only — minimises latency for real-time feel
            # Pi 5 is fast enough that 2 buffers never overflow
            buffer_count=2,
        )

        self._picam.configure(config)
        self._picam.start()

        # Warm-up: let AE/AWB and autofocus converge
        logger.info("Camera warming up (2s for AE/AWB/AF convergence)...")
        time.sleep(2.0)
        logger.info(f"Camera ready - {capture_w}x{capture_h} HD @ {settings.CAMERA_FPS}fps")

    def _init_opencv(self) -> None:
        if self._cap:
            self._cap.release()
            self._cap = None

        source = settings.CAMERA_SOURCE.strip()
        if source:
            import urllib.request
            try:
                req = urllib.request.urlopen(source, timeout=5)
                req.close()
            except Exception as exc:
                raise RuntimeError(
                    f"Cannot reach IP Webcam at {source}: {exc}"
                )
            self._ip_stream_source = source
            self._cap = None
            logger.info(f"IP Webcam confirmed reachable: {source}")
            return

        self._ip_stream_source = None

        # Scan indices 0-35 — Pi 5 CSI camera is at higher indices
        for idx in range(0, 36):
            try:
                cap = cv2.VideoCapture(idx)
                if not cap.isOpened():
                    cap.release()
                    continue
                ret, frame = cap.read()
                if not ret or frame is None:
                    cap.release()
                    continue
                cap.set(cv2.CAP_PROP_FRAME_WIDTH,  settings.CAMERA_WIDTH)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, settings.CAMERA_HEIGHT)
                cap.set(cv2.CAP_PROP_FPS,          settings.CAMERA_FPS)
                cap.set(cv2.CAP_PROP_BUFFERSIZE,   1)
                self._cap = cap
                logger.info(f"Camera opened at index {idx} (/dev/video{idx})")
                return
            except Exception as exc:
                logger.debug(f"Camera index {idx} failed: {exc}")
                continue
        raise RuntimeError("No camera device found at indices 0-35")

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

    # ── Frame read ────────────────────────────────────────────

    def _read_frame(self) -> np.ndarray | None:
        if PICAMERA_AVAILABLE and self._picam:
            # imx708 outputs RGB888 — must convert to BGR for OpenCV
            # This is the ONLY colour conversion — no other processing
            rgb = self._picam.capture_array("main")
            return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

        if self._ip_stream_source:
            return self._read_ip_frame()

        if self._cap is None:
            return None
        # Flush stale frames — keep buffer current
        self._cap.grab()
        ret, frame = self._cap.retrieve()
        return frame if ret else None

    def _read_ip_frame(self) -> np.ndarray | None:
        import urllib.request

        base = self._ip_stream_source.rstrip('/')
        if base.endswith('/video'):
            snapshot_url = base[:-6] + '/shot.jpg'
        elif base.endswith('/videofeed'):
            snapshot_url = base[:-10] + '/shot.jpg'
        else:
            snapshot_url = base.split('?')[0].rstrip('/') + '/shot.jpg'

        for attempt in range(2):
            try:
                with urllib.request.urlopen(snapshot_url, timeout=3) as resp:
                    data = resp.read()
                if not data:
                    continue
                arr   = np.frombuffer(data, dtype=np.uint8)
                frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if frame is not None:
                    h, w = frame.shape[:2]
                    tw, th = settings.CAMERA_WIDTH, settings.CAMERA_HEIGHT
                    if w != tw or h != th:
                        frame = cv2.resize(frame, (tw, th), interpolation=cv2.INTER_LINEAR)
                    return frame
            except Exception as exc:
                if attempt == 0:
                    time.sleep(0.1)
                else:
                    logger.debug(f"IP frame fetch failed: {exc}")
        return None

    # ── FPS tracking ──────────────────────────────────────────

    def _update_fps(self) -> None:
        self._frame_count += 1
        elapsed = time.time() - self._fps_timer
        if elapsed >= 1.0:
            self._fps_actual  = self._frame_count / elapsed
            self._frame_count = 0
            self._fps_timer   = time.time()


# Singleton
camera_manager = CameraManager()
