"""
Raspberry Pi Camera Module 3 - High-Performance Frame Acquisition

Architecture:
  - Producer thread: continuously grabs frames from picamera2 at 30fps
  - Consumer thread: processes frames (detection, JPEG encode)
  - Queue-based decoupling: heavy CV workloads never block camera stream
  - Zero-copy frame passing using numpy arrays

Performance targets:
  - Camera: 30fps continuous capture (1280x720 or 1920x1080)
  - Stream: 20fps JPEG output (smooth, no lag)
  - Detection: 10-15fps (heavy workload, runs independently)
"""

from __future__ import annotations

import logging
import threading
import time
import queue
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import cv2
import numpy as np

from backend.core.config import settings

logger = logging.getLogger(__name__)

try:
    from picamera2 import Picamera2
    PICAMERA_AVAILABLE = True
except ImportError:
    PICAMERA_AVAILABLE = False
    logger.warning("picamera2 not found - OpenCV fallback")


# ──────────────────────────────────────────────────────────
# Camera State
# ──────────────────────────────────────────────────────────

class CameraState(str, Enum):
    STOPPED      = "stopped"
    STARTING     = "starting"
    RUNNING      = "running"
    RECONNECTING = "reconnecting"
    ERROR        = "error"


@dataclass
class CameraFrame:
    """Zero-copy frame container"""
    frame: np.ndarray
    timestamp: float
    frame_number: int


# ──────────────────────────────────────────────────────────
# High-Performance Camera Manager
# ──────────────────────────────────────────────────────────

class CameraManagerRefactored:
    """
    Producer-consumer camera architecture for Raspberry Pi 5.
    
    Producer thread:
      - Grabs frames from picamera2 at full camera FPS (30fps)
      - Puts frames in a queue (maxsize=2 - always freshest)
      - Never blocks on consumer workload
    
    Consumer:
      - Pulls frames from queue (non-blocking)
      - Processing happens outside camera thread
      - Heavy CV operations don't freeze stream
    """

    def __init__(self):
        self._state = CameraState.STOPPED
        self._lock  = threading.Lock()
        
        # Frame queue - size 2 means only 2 most recent frames buffered
        # If consumer is slow, oldest frames are dropped (not displayed)
        self._frame_queue: queue.Queue[CameraFrame] = queue.Queue(maxsize=2)
        
        # Latest frame for immediate access (webcam display)
        self._latest_frame: Optional[np.ndarray] = None
        self._latest_timestamp = 0.0
        
        # Hardware
        self._picam: Optional[Picamera2] = None
        self._cap: Optional[cv2.VideoCapture] = None
        
        # Threads
        self._producer_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        # Metrics
        self._frame_count = 0
        self._frame_number = 0
        self._fps_actual = 0.0
        self._fps_timer = time.time()
        self._consecutive_failures = 0
        self._last_error = ""

    # ── Lifecycle ─────────────────────────────────────────

    def start(self) -> None:
        """Start camera producer thread"""
        if self._state not in (CameraState.STOPPED, CameraState.ERROR):
            return
        
        self._state = CameraState.STARTING
        self._stop_event.clear()
        
        self._producer_thread = threading.Thread(
            target=self._producer_loop,
            daemon=True,
            name="camera-producer"
        )
        self._producer_thread.start()
        logger.info("Camera producer thread started")

    def stop(self) -> None:
        """Stop camera and producer thread"""
        logger.info("Stopping camera...")
        self._state = CameraState.STOPPED
        self._stop_event.set()
        
        if self._producer_thread and self._producer_thread.is_alive():
            self._producer_thread.join(timeout=3)
        
        self._release_hardware()
        logger.info("Camera stopped")

    @property
    def state(self) -> CameraState:
        return self._state

    @property
    def is_running(self) -> bool:
        return self._state == CameraState.RUNNING

    @property
    def fps(self) -> float:
        return round(self._fps_actual, 1)

    @property
    def stats(self) -> dict:
        return {
            "state": self._state.value,
            "fps": self.fps,
            "frame_count": self._frame_number,
            "queue_size": self._frame_queue.qsize(),
            "last_error": self._last_error,
        }

    # ── Frame Access (Non-blocking) ───────────────────────

    def get_frame(self) -> Optional[np.ndarray]:
        """
        Get latest frame (non-blocking).
        Returns immediately with most recent frame or None.
        """
        with self._lock:
            if self._latest_frame is not None:
                return self._latest_frame.copy()
        return None

    def get_frame_for_detection(self) -> Optional[CameraFrame]:
        """
        Get next frame from queue for heavy processing (detection).
        Non-blocking - returns None if queue is empty.
        Consumer should call this at its own pace (10-15fps).
        """
        try:
            return self._frame_queue.get_nowait()
        except queue.Empty:
            return None

    def get_jpeg(self, quality: int = 85) -> Optional[bytes]:
        """Encode latest frame as JPEG"""
        frame = self.get_frame()
        if frame is None:
            return None
        
        ok, buf = cv2.imencode(
            ".jpg", frame,
            [cv2.IMWRITE_JPEG_QUALITY, quality,
             cv2.IMWRITE_JPEG_PROGRESSIVE, 1]
        )
        return bytes(buf) if ok else None

    # ── Producer Loop (Runs in separate thread) ───────────

    def _producer_loop(self) -> None:
        """
        Producer: continuously grab frames at camera FPS.
        Never blocks on consumer - if queue is full, drop oldest frame.
        """
        backoff = settings.CAMERA_RECONNECT_DELAY

        while not self._stop_event.is_set():
            # Initialize hardware
            try:
                self._init_hardware()
                self._state = CameraState.RUNNING
                self._consecutive_failures = 0
                backoff = settings.CAMERA_RECONNECT_DELAY
                logger.info("Camera initialized - entering capture loop")
            except Exception as exc:
                self._last_error = str(exc)
                logger.error(f"Camera init failed: {exc}")
                self._state = CameraState.RECONNECTING
                self._release_hardware()
                self._sleep_interruptible(backoff)
                backoff = min(backoff * 2, 60)
                continue

            # Frame capture loop
            frame_interval = 1.0 / max(settings.CAMERA_FPS, 1)
            next_frame_time = time.time()

            while self._state == CameraState.RUNNING and not self._stop_event.is_set():
                # Rate limiting
                now = time.time()
                sleep_time = next_frame_time - now
                if sleep_time > 0:
                    time.sleep(sleep_time)
                next_frame_time = time.time() + frame_interval

                try:
                    # Grab frame (fast - no processing)
                    frame = self._read_frame()
                    if frame is None:
                        self._on_failure("read_frame returned None")
                        continue

                    # Update latest frame (for webcam display - 30fps)
                    with self._lock:
                        self._latest_frame = frame
                        self._latest_timestamp = now

                    # Put in queue for detection (non-blocking)
                    # If queue is full, remove oldest frame first
                    self._frame_number += 1
                    camera_frame = CameraFrame(
                        frame=frame,
                        timestamp=now,
                        frame_number=self._frame_number
                    )
                    
                    try:
                        self._frame_queue.put_nowait(camera_frame)
                    except queue.Full:
                        # Queue full - drop oldest, add newest
                        try:
                            self._frame_queue.get_nowait()
                        except queue.Empty:
                            pass
                        self._frame_queue.put_nowait(camera_frame)

                    self._consecutive_failures = 0
                    self._update_fps()

                except Exception as exc:
                    self._on_failure(str(exc))

            if self._state == CameraState.RECONNECTING:
                logger.warning("Camera reconnecting...")
                self._release_hardware()
                self._sleep_interruptible(backoff)
                backoff = min(backoff * 2, 60)

        self._release_hardware()

    def _on_failure(self, reason: str) -> None:
        self._consecutive_failures += 1
        self._last_error = reason

        if self._consecutive_failures == 1:
            logger.warning(f"Camera read failure: {reason}")
        elif self._consecutive_failures % 10 == 0:
            logger.error(f"Camera: {self._consecutive_failures} consecutive failures")

        if self._consecutive_failures >= settings.CAMERA_MAX_FAILURES:
            self._state = CameraState.RECONNECTING
        else:
            time.sleep(0.02)

    def _sleep_interruptible(self, seconds: float) -> None:
        """Sleep that can be interrupted by stop event"""
        self._stop_event.wait(timeout=seconds)

    # ── Hardware Init ─────────────────────────────────────

    def _init_hardware(self) -> None:
        """Initialize camera hardware"""
        if PICAMERA_AVAILABLE:
            self._init_picam()
        else:
            self._init_opencv()

    def _init_picam(self) -> None:
        """
        Initialize Raspberry Pi Camera Module 3.
        
        Optimizations:
        - 1280x720 or 1920x1080 based on settings
        - Continuous autofocus (AfMode=2)
        - Fast AE response
        - Neutral colour (no saturation boost)
        - RGB888 format (converted to BGR once)
        """
        if self._picam:
            try:
                self._picam.stop()
                self._picam.close()
            except Exception:
                pass
        
        self._picam = Picamera2()
        
        # Resolution - prefer 720p for speed, 1080p for quality
        capture_w = min(settings.CAMERA_WIDTH, 1920)
        capture_h = min(settings.CAMERA_HEIGHT, 1080)
        
        config = self._picam.create_video_configuration(
            main={
                "size": (capture_w, capture_h),
                "format": "RGB888",
            },
            controls={
                # Fast AE: 16-50ms frame duration
                "FrameDurationLimits": (16_666, 50_000),
                
                # Auto exposure and white balance
                "AeEnable": True,
                "AwbEnable": True,
                "AeMeteringMode": 0,  # centre-weighted
                "AeExposureMode": 0,  # normal
                
                # Continuous autofocus - always sharp
                "AfMode": 2,  # continuous AF
                "AfSpeed": 1,  # fast AF
                
                # Neutral colours (true bean colour)
                "NoiseReductionMode": 2,  # fast
                "Sharpness": 1.5,
                "Contrast": 1.0,  # neutral
                "Saturation": 1.0,  # neutral
                "Brightness": 0.0,
            },
            buffer_count=2,  # minimal latency
        )
        
        self._picam.configure(config)
        self._picam.start()
        
        # Warm-up for AE/AWB/AF
        logger.info("Camera warming up (2s)...")
        time.sleep(2.0)
        logger.info(f"Camera ready - {capture_w}x{capture_h} @ {settings.CAMERA_FPS}fps")

    def _init_opencv(self) -> None:
        """Fallback: OpenCV VideoCapture"""
        if self._cap:
            self._cap.release()
        
        # Scan for camera
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
                
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, settings.CAMERA_WIDTH)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, settings.CAMERA_HEIGHT)
                cap.set(cv2.CAP_PROP_FPS, settings.CAMERA_FPS)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                
                self._cap = cap
                logger.info(f"OpenCV camera at index {idx}")
                return
            except Exception:
                continue
        
        raise RuntimeError("No camera found")

    def _release_hardware(self) -> None:
        """Release camera hardware"""
        if self._picam:
            try:
                self._picam.stop()
                self._picam.close()
            except Exception:
                pass
            self._picam = None
        
        if self._cap:
            self._cap.release()
            self._cap = None

    # ── Frame Read ────────────────────────────────────────

    def _read_frame(self) -> Optional[np.ndarray]:
        """Read one frame from hardware"""
        if self._picam:
            # picamera2: RGB888 -> BGR for OpenCV
            rgb = self._picam.capture_array("main")
            return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        
        if self._cap:
            # Flush buffer
            self._cap.grab()
            ret, frame = self._cap.retrieve()
            return frame if ret else None
        
        return None

    # ── Metrics ───────────────────────────────────────────

    def _update_fps(self) -> None:
        """Update FPS counter"""
        self._frame_count += 1
        elapsed = time.time() - self._fps_timer
        if elapsed >= 1.0:
            self._fps_actual = self._frame_count / elapsed
            self._frame_count = 0
            self._fps_timer = time.time()


# Singleton
camera_manager_refactored = CameraManagerRefactored()
