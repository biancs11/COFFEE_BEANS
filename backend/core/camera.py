"""
Raspberry Pi Camera - Zero-latency LIFO capture.

Optimized for Raspberry Pi 5 + Camera Module 3 (imx708):
  - 640x480 @ 30fps (optimized for bandwidth)
  - LIFO frame buffer (maxsize=1) - ALWAYS fresh frames
  - True colour: Picamera2 RGB888 arrays passed to OpenCV in BGR byte order
  - Zero delay: capture thread never blocks
  - Continuous autofocus enabled
"""

from __future__ import annotations

import logging
import threading
import time
import os
import queue
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
    Thread-safe zero-latency camera with LIFO frame buffer.
    
    Architecture:
    - Dedicated capture thread runs at maximum speed (no sleep/throttling)
    - LIFO queue (maxsize=1) ensures consumers always get newest frame
    - Old frames are instantly dropped when new ones arrive
    - No locks on hot path - queue handles thread safety
    """

    _FAILURE_THRESHOLD: int = settings.CAMERA_MAX_FAILURES

    def __init__(self):
        # A single-slot FIFO with drop-oldest writes always holds the newest frame.
        self._frame_queue: queue.Queue = queue.Queue(maxsize=1)
        
        self._state                    = CameraState.STOPPED
        self._thread: threading.Thread | None = None

        self._fps_actual           = 0.0
        self._frame_count          = 0
        self._fps_timer            = time.time()
        self._consecutive_failures = 0
        self._total_frames         = 0
        self._dropped_frames       = 0
        self._reconnect_count      = 0
        self._last_error: str      = ""

        self._picam                              = None
        self._cap: cv2.VideoCapture | None       = None
        self._ip_stream_source: str | None       = None
        self._ip_stream_bytes                    = b""
        # Warm/cool adjustment: -50 is cooler, +50 is warmer, 0 is neutral.
        self._color_balance = 0.0

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
            "dropped_frames":       self._dropped_frames,
            "drop_rate_pct":        round(100 * self._dropped_frames / max(self._total_frames, 1), 1),
            "reconnect_count":      self._reconnect_count,
            "last_error":           self._last_error,
            "consecutive_failures": self._consecutive_failures,
        }

    def get_frame(self) -> np.ndarray | None:
        """Get the newest frame (non-blocking, LIFO behavior)"""
        try:
            # Get newest frame immediately, non-blocking
            frame = self._frame_queue.get_nowait()
            return frame.copy()
        except queue.Empty:
            return None

    @property
    def color_balance(self) -> float:
        return self._color_balance

    def set_color_balance(self, value: float) -> float:
        """Set warm/cool channel balance in the supported -50..50 range."""
        self._color_balance = float(max(-50.0, min(50.0, value)))
        return self._color_balance

    def _apply_color_balance(self, frame: np.ndarray | None) -> np.ndarray | None:
        """Apply a modest BGR warm/cool correction before display and detection."""
        if frame is None or self._color_balance == 0:
            return frame

        adjustment = self._color_balance / 250.0  # up to +/-20% red/blue gain
        matrix = np.array([
            [1.0 - adjustment, 0.0, 0.0],  # B
            [0.0, 1.0, 0.0],              # G
            [0.0, 0.0, 1.0 + adjustment],  # R
        ], dtype=np.float32)
        return cv2.transform(frame, matrix)

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
        """
        Main capture loop - runs at MAXIMUM speed (no throttling).
        
        Critical: This loop NEVER sleeps or waits for consumers.
        If consumers are slow, frames are dropped (LIFO behavior).
        """
        backoff = settings.CAMERA_RECONNECT_DELAY

        while self._state != CameraState.STOPPED:
            try:
                self._initialise()
                self._state                = CameraState.RUNNING
                self._consecutive_failures = 0
                backoff                    = settings.CAMERA_RECONNECT_DELAY
                logger.info("Camera initialised - entering zero-latency capture loop")
            except Exception as exc:
                self._last_error = str(exc)
                logger.error(f"Camera init failed: {exc}")
                self._state = CameraState.RECONNECTING
                self._release()
                self._sleep_backoff(backoff)
                backoff = min(backoff * 2, 60)
                continue

            # ═══ ZERO-LATENCY CAPTURE LOOP ═══
            # No sleep, no throttling - capture as fast as possible
            while self._state == CameraState.RUNNING:
                try:
                    frame = self._read_frame()
                    if frame is None:
                        self._on_failure("read_frame returned None")
                        continue

                    # Replace any queued frame so a slow consumer never sees stale video.
                    self._put_latest_frame(frame)

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

    def _put_latest_frame(self, frame: np.ndarray) -> None:
        """Insert without blocking, evicting the stale slot if necessary."""
        while True:
            try:
                self._frame_queue.put_nowait(frame)
                return
            except queue.Full:
                try:
                    self._frame_queue.get_nowait()
                    self._dropped_frames += 1
                except queue.Empty:
                    # A consumer freed the slot between Full and get_nowait.
                    continue

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
        """Try configured and locally attached cameras, then fail with all causes."""
        failures: list[str] = []

        # An explicitly configured network camera remains the preferred source.
        if settings.CAMERA_SOURCE.strip():
            try:
                self._init_opencv()
                return
            except Exception as exc:
                failures.append(f"configured camera: {exc}")
                self._release()

        # Picamera2 is the supported path for Raspberry Pi Camera Module 3.
        # Package presence alone does not prove a camera is connected, so fall
        # through to OpenCV if construction/configuration/start fails.
        if PICAMERA_AVAILABLE:
            try:
                self._init_picam()
                return
            except Exception as exc:
                failures.append(f"Picamera2: {exc}")
                self._release()

        try:
            self._init_opencv(local_only=True)
            return
        except Exception as exc:
            failures.append(f"local webcam: {exc}")

        raise RuntimeError("; ".join(failures))

    def _init_picam(self) -> None:
        """
        Initialise Camera Module 3 for zero-latency 640x480 capture.

        Key optimizations:
        - 640x480 resolution (optimized for Pi 5 memory bandwidth)
        - RGB888 format (Picamera2 array is already in BGR byte order)
        - buffer_count=1 (minimum buffering for zero lag)
        - Continuous autofocus enabled
        - Anti-glare exposure settings
        """
        if self._picam:
            try:
                self._picam.stop()
                self._picam.close()
            except Exception:
                pass
            self._picam = None

        self._picam = Picamera2()

        # Lock to 640x480 for optimal bandwidth
        capture_w = 640
        capture_h = 480

        config = self._picam.create_video_configuration(
            main={
                "size":   (capture_w, capture_h),
                "format": "RGB888",  # Will be converted to BGR
            },
            # CRITICAL: buffer_count=1 for zero latency
            # Higher values accumulate stale frames
            buffer_count=1,
        )

        self._picam.configure(config)
        self._picam.start()

        # Controls vary across libcamera and Picamera2 versions. Apply each
        # independently so an unsupported optional control cannot disable
        # the otherwise compatible Camera Module 3 stream.
        controls = {
            "AfMode": 2, "AfSpeed": 1,
            "AeEnable": True, "AwbEnable": True,
            "AeConstraintMode": 1, "ExposureValue": -0.5,
            "FrameDurationLimits": (16_666, 33_333),
            "NoiseReductionMode": 2, "Sharpness": 1.5,
            "Contrast": 1.0, "Saturation": 1.0, "Brightness": 0.0,
        }
        for name, value in controls.items():
            try:
                self._picam.set_controls({name: value})
            except Exception as exc:
                logger.debug("Ignoring unsupported Picamera2 control %s: %s", name, exc)

        # Brief warm-up for AE/AWB/AF (reduced from 2s to 0.5s since we're at 640x480)
        logger.info("Camera warming up (0.5s for AE/AWB/AF)...")
        time.sleep(0.5)
        logger.info(f"Zero-latency camera ready - {capture_w}x{capture_h} @ max FPS")
        logger.info("LIFO mode: Old frames dropped instantly, always fresh capture")

    def _init_opencv(self, local_only: bool = False) -> None:
        if self._cap:
            self._cap.release()
            self._cap = None

        source = settings.CAMERA_SOURCE.strip()
        if source and not local_only:
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

        # CSI Module 3 should be opened through Picamera2/libcamera. Keep a
        # bounded index scan for laptop and USB webcams to avoid long stalls.
        for idx in range(0, 10):
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
        raise RuntimeError("No local camera found at indices 0-9")

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

        # Clear the queue
        try:
            while True:
                self._frame_queue.get_nowait()
        except queue.Empty:
            pass

    # ── Frame read ────────────────────────────────────────────

    def _read_frame(self) -> np.ndarray | None:
        """
        Read frame from camera in OpenCV's BGR channel order.

        Picamera2's RGB888 capture_array is laid out as BGR bytes.
        """
        if PICAMERA_AVAILABLE and self._picam:
            return self._apply_color_balance(self._picam.capture_array("main"))

        if self._ip_stream_source:
            return self._apply_color_balance(self._read_ip_frame())

        if self._cap is None:
            return None
        
        # OpenCV fallback - already in BGR format
        ret, frame = self._cap.read()
        return self._apply_color_balance(frame if ret else None)

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
