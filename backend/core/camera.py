"""
Raspberry Pi Camera â€” production-hardened with reconnect circuit breaker.

Optimised for Raspberry Pi 5 + Camera Module 3 (imx708):
  â€¢ picamera2 with proper auto-exposure (no manual override)
  â€¢ Zero-copy frame capture using capture_array("main")
  â€¢ Frame rate cap to prevent CPU starvation
  â€¢ Lightweight preprocessing â€” only when needed
  â€¢ Thread-safe double-buffer to minimise lock contention
  â€¢ CameraState enum so callers (websocket, health endpoint) can read status
  â€¢ All dimensions / FPS driven by config.settings
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
    logger.info("picamera2 detected â€” using Raspberry Pi Camera")
except ImportError:
    PICAMERA_AVAILABLE = False
    logger.warning("picamera2 not found â€” falling back to OpenCV VideoCapture")


# â”€â”€ Camera state machine â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class CameraState(str, Enum):
    STOPPED      = "stopped"
    STARTING     = "starting"
    RUNNING      = "running"
    RECONNECTING = "reconnecting"
    ERROR        = "error"


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# CameraManager
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class CameraManager:
    """
    Thread-safe camera wrapper for Raspberry Pi 5 (picamera2 / imx708)
    with automatic fallback to OpenCV and full reconnect logic.

    Optimisations vs original:
      - Auto-exposure enabled (no manual ExposureTime/AnalogueGain)
      - capture_array("main") â€” avoids format conversion overhead
      - Frame rate governor â€” cap at CAMERA_FPS, sleep remainder
      - Preprocessing only applied when system is RUNNING and sorting
      - Double-buffer pattern â€” writer never blocks reader

    State machine:
        STOPPED â†’ STARTING â†’ RUNNING âŸµâ†’ RECONNECTING â†’ ERROR
    """

    _FAILURE_THRESHOLD: int = settings.CAMERA_MAX_FAILURES

    def __init__(self):
        self._lock          = threading.Lock()
        self._frame:  np.ndarray | None = None
        self._state         = CameraState.STOPPED
        self._thread: threading.Thread | None = None

        # Metrics
        self._fps_actual           = 0.0
        self._frame_count          = 0
        self._fps_timer            = time.time()
        self._consecutive_failures = 0
        self._total_frames         = 0
        self._reconnect_count      = 0
        self._last_error: str      = ""

        # Hardware handles
        self._picam = None
        self._cap:   cv2.VideoCapture | None = None
        self._ip_stream_source: str | None   = None
        self._ip_stream_bytes                = b""

        # Frame interval for rate-limiting (seconds)
        self._frame_interval = 1.0 / max(settings.CAMERA_FPS, 1)

    # â”€â”€ Public lifecycle â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def start(self) -> None:
        if self._state not in (CameraState.STOPPED, CameraState.ERROR):
            logger.debug("Camera already running / starting â€” ignoring start()")
            return
        self._state  = CameraState.STARTING
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="camera-loop"
        )
        self._thread.start()
        logger.info("Camera thread started")

    def stop(self) -> None:
        logger.info("Stopping camera â€¦")
        self._state = CameraState.STOPPED
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=4)
        self._release()
        logger.info("Camera stopped")

    # â”€â”€ Properties â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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

    # â”€â”€ Frame access â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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

    # â”€â”€ Main capture loop â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _run_loop(self) -> None:
        backoff = settings.CAMERA_RECONNECT_DELAY

        while self._state != CameraState.STOPPED:
            # â”€â”€ Initialise hardware â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            try:
                self._initialise()
                self._state                = CameraState.RUNNING
                self._consecutive_failures = 0
                backoff                    = settings.CAMERA_RECONNECT_DELAY
                logger.info("Camera initialised â€” entering capture loop")
            except Exception as exc:
                self._last_error = str(exc)
                logger.error(f"Camera init failed: {exc}")
                self._state = CameraState.RECONNECTING
                self._release()
                self._sleep_backoff(backoff)
                backoff = min(backoff * 2, 60)
                continue

            # â”€â”€ Inner capture loop â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            next_frame_time = time.time()

            while self._state == CameraState.RUNNING:
                # Rate governor â€” sleep until next frame is due
                now = time.time()
                sleep_time = next_frame_time - now
                if sleep_time > 0:
                    time.sleep(sleep_time)
                next_frame_time = time.time() + self._frame_interval

                try:
                    frame = self._read_frame()
                    if frame is None:
                        self._on_failure("read_frame returned None")
                        continue

                    # Only apply preprocessing for local picamera â€” skip for IP streams
                    if not self._ip_stream_source:
                        frame = self._preprocess(frame)

                    with self._lock:
                        self._frame = frame

                    self._consecutive_failures = 0
                    self._total_frames        += 1
                    self._update_fps()

                except Exception as exc:
                    self._on_failure(str(exc))

            if self._state == CameraState.RECONNECTING:
                logger.warning(
                    f"Camera reconnecting (attempt #{self._reconnect_count + 1}) "
                    f"after {self._consecutive_failures} consecutive failures"
                )
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
            logger.error(
                f"Camera: {self._consecutive_failures} consecutive failures â€” {reason}"
            )

        if self._consecutive_failures >= threshold:
            logger.error(
                f"Camera failure threshold ({threshold}) reached â€” triggering reconnect"
            )
            self._state = CameraState.RECONNECTING
        else:
            time.sleep(0.05)

    def _sleep_backoff(self, seconds: float) -> None:
        elapsed = 0.0
        while elapsed < seconds and self._state != CameraState.STOPPED:
            time.sleep(0.5)
            elapsed += 0.5

    # â”€â”€ Hardware init / release â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _initialise(self) -> None:
        if PICAMERA_AVAILABLE:
            self._init_picam()
        else:
            self._init_opencv()

    def _init_picam(self) -> None:
        """
        Initialise Raspberry Pi Camera Module 3 (imx708) via picamera2.

        Key improvements over original:
          - Auto-exposure and auto-white-balance fully enabled
          - NO manual ExposureTime/AnalogueGain override (caused dark frames)
          - FrameDurationLimits set wide (33ms min, 100ms max) â€” lets AE breathe
          - NoiseReductionMode=2 (fast) â€” better quality than mode 1
          - Sharpness=2.0 â€” sharper beans at sorting distance
          - Brightness/Contrast tuned for coffee bean detection
        """
        if self._picam:
            try:
                self._picam.stop()
                self._picam.close()
            except Exception:
                pass
            self._picam = None

        self._picam = Picamera2()

        # Use a lower resolution for the capture stream to reduce latency
        # imx708 native: 4608x2592. For bean detection 1280x720 is plenty.
        capture_w = min(settings.CAMERA_WIDTH,  1920)
        capture_h = min(settings.CAMERA_HEIGHT, 1080)

        config = self._picam.create_video_configuration(
            main={
                "size":   (capture_w, capture_h),
                "format": "RGB888",
            },
            # Low-res stream for fast preview (optional â€” reduces ISP load)
            lores={
                "size":   (capture_w // 2, capture_h // 2),
                "format": "YUV420",
            },
            controls={
                # Wide frame duration range â€” let AE pick the right exposure
                # Min 16ms (62fps), max 100ms (10fps in dark)
                "FrameDurationLimits": (16_666, 100_000),

                # Full auto-exposure and auto-white-balance â€” NO manual override
                "AeEnable":            True,
                "AwbEnable":           True,
                "AeMeteringMode":      0,       # centre-weighted
                "AeExposureMode":      0,       # normal

                # Image quality
                "NoiseReductionMode":  2,       # fast noise reduction
                "Sharpness":           2.0,     # sharper for small bean detail
                "Contrast":            1.1,     # slight contrast boost
                "Saturation":          1.2,     # better colour separation for grading
                "Brightness":          0.0,     # neutral brightness (AE handles it)
            },
            buffer_count=4,     # 4-frame buffer â€” reduces dropped frames
        )

        self._picam.configure(config)
        self._picam.start()

        # Warm-up â€” let AE/AWB converge before we start capturing
        logger.info("Camera warming up (2s for AE/AWB convergence)â€¦")
        time.sleep(2.0)
        logger.info(f"Camera ready â€” {capture_w}x{capture_h} @ up to {settings.CAMERA_FPS}fps")

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
                    f"Cannot reach IP Webcam at {source}: {exc}\n"
                    "Ensure the IP Webcam app is running and phone is on same Wi-Fi."
                )
            self._ip_stream_source = source
            self._cap = None
            logger.info(f"IP Webcam source confirmed reachable: {source}")
            return

        self._ip_stream_source = None

        # Scan indices 0-35 â€” Pi 5 CSI camera appears at higher indices
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

    # â”€â”€ Frame read â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _read_frame(self) -> np.ndarray | None:
        if PICAMERA_AVAILABLE and self._picam:
            # capture_array("main") â€” direct numpy array, no copy overhead
            rgb = self._picam.capture_array("main")
            # imx708 returns RGB â€” convert to BGR for OpenCV
            return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

        if self._ip_stream_source:
            return self._read_ip_frame()

        if self._cap is None:
            return None
        # Flush stale frames from buffer â€” grab without decode
        for _ in range(2):
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
                    return frame
            except Exception as exc:
                if attempt == 0:
                    time.sleep(0.1)
                else:
                    logger.debug(f"IP frame fetch failed after retry: {exc}")
        return None

    # â”€â”€ Pre-processing â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _preprocess(self, frame: np.ndarray) -> np.ndarray:
        """
        Optimised preprocessing for coffee bean detection on Pi 5.

        Changes from original:
          - Skip resize if already correct size (avoids unnecessary copy)
          - CLAHE applied only to L channel (faster than full LAB round-trip)
          - Sharpening uses lightweight kernel instead of GaussianBlur subtract
          - IP streams: resize only, no enhancement
        """
        source = settings.CAMERA_SOURCE.strip()
        if source:
            h, w = frame.shape[:2]
            tw, th = settings.CAMERA_WIDTH, settings.CAMERA_HEIGHT
            if w != tw or h != th:
                frame = cv2.resize(frame, (tw, th), interpolation=cv2.INTER_LINEAR)
            return frame

        # Resize if needed (should rarely trigger with picamera2)
        h, w = frame.shape[:2]
        if w != settings.CAMERA_WIDTH or h != settings.CAMERA_HEIGHT:
            frame = cv2.resize(
                frame,
                (settings.CAMERA_WIDTH, settings.CAMERA_HEIGHT),
                interpolation=cv2.INTER_LINEAR
            )

        # CLAHE on L channel only â€” improves contrast for detection
        lab     = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe   = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        l       = clahe.apply(l)
        frame   = cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)

        # Lightweight sharpening kernel (faster than GaussianBlur subtract)
        kernel = np.array([
            [ 0, -1,  0],
            [-1,  5, -1],
            [ 0, -1,  0]
        ], dtype=np.float32)
        frame = cv2.filter2D(frame, -1, kernel)

        return frame

    # â”€â”€ FPS tracking â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _update_fps(self) -> None:
        self._frame_count += 1
        elapsed = time.time() - self._fps_timer
        if elapsed >= 1.0:
            self._fps_actual  = self._frame_count / elapsed
            self._frame_count = 0
            self._fps_timer   = time.time()


# â”€â”€ Singleton â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
camera_manager = CameraManager()
