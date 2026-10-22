"""
Concurrent Multi-Node Graph Pipeline for Real-Time Coffee Bean Scanning

Architecture: Directed Acyclic Graph (DAG) with concurrent execution nodes

Execution Graph:
                    ┌──────────────────┐
                    │  Capture Node    │ (Producer)
                    │  30fps @ 640x480 │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │  Frame Queue(2)  │ (Thread-safe FIFO)
                    └────────┬─────────┘
                             │
                ┌────────────┴────────────┐
                │                         │
    ┌───────────▼──────────┐   ┌─────────▼──────────┐
    │  Vision Node         │   │  Autofocus Node    │
    │  Detection @ 10-15fps│   │  Continuous AF     │
    └───────────┬──────────┘   └────────────────────┘
                │
    ┌───────────▼──────────┐
    │  Display/Stream Node │ (20fps smooth)
    │  JPEG encode & WS    │
    └──────────────────────┘

Performance targets:
- Capture: 30fps (never blocks)
- Display: 20fps (smooth, no lag)
- Detection: 10-15fps (heavy CV, async)
- Autofocus: Continuous (always sharp)
- Total latency: <50ms capture-to-display

Raspberry Pi 5 + Camera Module 3 optimized
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Callable
import numpy as np
import cv2

logger = logging.getLogger(__name__)

try:
    from picamera2 import Picamera2
    from libcamera import controls
    PICAMERA_AVAILABLE = True
except ImportError:
    PICAMERA_AVAILABLE = False
    logger.warning("picamera2 not available - using OpenCV fallback")


# ══════════════════════════════════════════════════════════
# Data Structures
# ══════════════════════════════════════════════════════════

class NodeState(str, Enum):
    """Execution state of a graph node"""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"
    STOPPED = "stopped"


@dataclass
class Frame:
    """Zero-copy frame container with metadata"""
    data: np.ndarray
    timestamp: float
    frame_id: int
    metadata: dict


@dataclass
class NodeMetrics:
    """Performance metrics for a graph node"""
    state: NodeState
    frames_processed: int
    fps: float
    avg_latency_ms: float
    errors: int
    last_error: str


# ══════════════════════════════════════════════════════════
# Base Graph Node
# ══════════════════════════════════════════════════════════

class GraphNode:
    """
    Base class for graph execution nodes.
    Each node runs in its own thread with metrics tracking.
    """
    
    def __init__(self, name: str):
        self.name = name
        self._state = NodeState.IDLE
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        # Metrics
        self._frames_processed = 0
        self._fps = 0.0
        self._fps_counter = 0
        self._fps_timer = time.time()
        self._errors = 0
        self._last_error = ""
        self._latency_samples = []
        
        logger.info(f"[{self.name}] Node initialized")
    
    def start(self) -> None:
        """Start node execution thread"""
        if self._state == NodeState.RUNNING:
            return
        
        self._state = NodeState.RUNNING
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name=f"node-{self.name}"
        )
        self._thread.start()
        logger.info(f"[{self.name}] Node started")
    
    def stop(self) -> None:
        """Stop node execution"""
        logger.info(f"[{self.name}] Stopping node...")
        self._state = NodeState.STOPPED
        self._stop_event.set()
        
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        
        logger.info(f"[{self.name}] Node stopped")
    
    def pause(self) -> None:
        """Pause node execution"""
        self._state = NodeState.PAUSED
    
    def resume(self) -> None:
        """Resume node execution"""
        self._state = NodeState.RUNNING
    
    def _run(self) -> None:
        """Main execution loop - override in subclasses"""
        raise NotImplementedError
    
    def _update_fps(self) -> None:
        """Update FPS metric"""
        self._fps_counter += 1
        elapsed = time.time() - self._fps_timer
        if elapsed >= 1.0:
            self._fps = self._fps_counter / elapsed
            self._fps_counter = 0
            self._fps_timer = time.time()
    
    def _record_latency(self, latency_ms: float) -> None:
        """Record latency sample"""
        self._latency_samples.append(latency_ms)
        if len(self._latency_samples) > 100:
            self._latency_samples.pop(0)
    
    def _on_error(self, error: Exception) -> None:
        """Handle node error"""
        self._errors += 1
        self._last_error = str(error)
        logger.error(f"[{self.name}] Error: {error}")
    
    @property
    def metrics(self) -> NodeMetrics:
        """Get current node metrics"""
        avg_latency = (
            sum(self._latency_samples) / len(self._latency_samples)
            if self._latency_samples else 0.0
        )
        return NodeMetrics(
            state=self._state,
            frames_processed=self._frames_processed,
            fps=round(self._fps, 1),
            avg_latency_ms=round(avg_latency, 2),
            errors=self._errors,
            last_error=self._last_error
        )


# ══════════════════════════════════════════════════════════
# Node 1: Capture Node (Producer)
# ══════════════════════════════════════════════════════════

class CaptureNode(GraphNode):
    """
    Hardware frame capture node.
    Continuously grabs frames from Camera Module 3 at maximum speed.
    Pushes frames to output queue with zero processing overhead.
    """
    
    def __init__(
        self,
        output_queue: queue.Queue,
        width: int = 640,
        height: int = 480,
        fps: int = 30
    ):
        super().__init__("Capture")
        self.output_queue = output_queue
        self.width = width
        self.height = height
        self.target_fps = fps
        
        self._picam: Optional[Picamera2] = None
        self._cap: Optional[cv2.VideoCapture] = None
        self._frame_id = 0
        self._frames_dropped = 0  # Track dropped frames
    
    def _run(self) -> None:
        """Producer loop: grab frames and push to queue"""
        # Initialize hardware
        try:
            self._init_camera()
        except Exception as exc:
            self._on_error(exc)
            self._state = NodeState.ERROR
            return
        
        frame_interval = 1.0 / self.target_fps
        next_frame_time = time.time()
        
        while not self._stop_event.is_set():
            # Rate limiting
            now = time.time()
            sleep_time = next_frame_time - now
            if sleep_time > 0:
                time.sleep(sleep_time)
            next_frame_time = time.time() + frame_interval
            
            try:
                # Grab frame (fast - no processing)
                raw_frame = self._grab_frame()
                if raw_frame is None:
                    continue
                
                # Create frame object with metadata
                self._frame_id += 1
                frame = Frame(
                    data=raw_frame,
                    timestamp=now,
                    frame_id=self._frame_id,
                    metadata={
                        "node": self.name,
                        "capture_time": now,
                    }
                )
                
                # Push to queue (non-blocking - ALWAYS drop old frame)
                try:
                    self.output_queue.put_nowait(frame)
                except queue.Full:
                    # Queue full - FORCE drop old frame, add newest
                    # This guarantees detector ALWAYS gets freshest frame
                    try:
                        old_frame = self.output_queue.get_nowait()
                        self._frames_dropped += 1
                        if self._frames_dropped % 10 == 0:
                            logger.warning(f"[{self.name}] Dropped {self._frames_dropped} frames (detector too slow)")
                    except queue.Empty:
                        pass
                    self.output_queue.put_nowait(frame)
                
                self._frames_processed += 1
                self._update_fps()
            
            except Exception as exc:
                self._on_error(exc)
        
        # Cleanup
        self._release_camera()
    
    def _init_camera(self) -> None:
        """Initialize camera hardware"""
        if PICAMERA_AVAILABLE:
            self._init_picamera()
        else:
            self._init_opencv()
    
    def _init_picamera(self) -> None:
        """
        Initialize Raspberry Pi Camera Module 3 with optimized color/exposure.
        
        CRITICAL FIXES:
        1. Incandescent/Tungsten AWB mode for coffee bean lighting
        2. Exposure compensation +0.5 to +1.0 so beans don't appear black
        3. AeConstraintMode=Normal for full dynamic range
        4. Disable excessive contrast/saturation that causes clipping
        """
        self._picam = Picamera2()
        
        # Optimized config for 640x480 @ 30fps
        config = self._picam.create_video_configuration(
            main={
                "size": (self.width, self.height),
                "format": "RGB888",
            },
            controls={
                # Fast frame duration: 16-50ms
                "FrameDurationLimits": (16_666, 50_000),
                
                # CRITICAL: Auto exposure with NO constraint
                # Allows full dynamic range so light beans aren't black
                "AeEnable": True,
                "AeConstraintMode": controls.AeConstraintModeEnum.Normal,
                
                # CRITICAL: Exposure compensation +0.8 (range: -4.0 to +4.0)
                # Brightens image so light brown beans render correctly
                "ExposureValue": 0.8,
                
                # CRITICAL: Incandescent/Tungsten white balance
                # Coffee beans under warm LED/tungsten lighting
                "AwbEnable": True,
                "AwbMode": controls.AwbModeEnum.Incandescent,
                
                # Continuous autofocus - FAST mode
                "AfMode": controls.AfModeEnum.Continuous,
                "AfSpeed": controls.AfSpeedEnum.Fast,
                
                # Image quality - REDUCE to avoid clipping
                "NoiseReductionMode": controls.draft.NoiseReductionModeEnum.Fast,
                "Sharpness": 1.0,      # Reduced from 1.5 - avoid edge artifacts
                "Contrast": 1.0,       # Neutral - no clipping
                "Saturation": 1.0,     # Neutral - true bean colours
                "Brightness": 0.0,     # Let AE handle it
            },
            buffer_count=1,  # CRITICAL: Single buffer for minimum latency
        )
        
        self._picam.configure(config)
        self._picam.start()
        
        # Warm-up for AE/AWB/AF convergence
        time.sleep(1.5)
        
        logger.info(
            f"[{self.name}] Camera initialized: {self.width}x{self.height} @ {self.target_fps}fps | "
            f"AWB=Incandescent, ExposureValue=+0.8, buffer=1"
        )
    
    def _init_opencv(self) -> None:
        """Fallback: OpenCV VideoCapture"""
        for idx in range(10):
            cap = cv2.VideoCapture(idx)
            if cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                cap.set(cv2.CAP_PROP_FPS, self.target_fps)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                self._cap = cap
                logger.info(f"[{self.name}] OpenCV camera at index {idx}")
                return
        raise RuntimeError("No camera found")
    
    def _grab_frame(self) -> Optional[np.ndarray]:
        """Grab one frame from hardware"""
        if self._picam:
            # picamera2: RGB888 -> BGR for OpenCV
            rgb = self._picam.capture_array("main")
            return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        
        if self._cap:
            self._cap.grab()  # Flush buffer
            ret, frame = self._cap.retrieve()
            return frame if ret else None
        
        return None
    
    def _release_camera(self) -> None:
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


# ══════════════════════════════════════════════════════════
# Node 2: Vision Processing Node (Worker)
# ══════════════════════════════════════════════════════════

class VisionNode(GraphNode):
    """
    Heavy computer vision processing node.
    Pulls frames from input queue, runs detection, pushes to output.
    Runs independently - never blocks capture.
    """
    
    def __init__(
        self,
        input_queue: queue.Queue,
        output_queue: queue.Queue,
        detector_func: Optional[Callable] = None
    ):
        super().__init__("Vision")
        self.input_queue = input_queue
        self.output_queue = output_queue
        self.detector_func = detector_func
    
    def _run(self) -> None:
        """Worker loop: process frames from queue"""
        while not self._stop_event.is_set():
            try:
                # Pull frame from queue (blocking with SHORT timeout)
                # Short timeout ensures we check stop_event frequently
                try:
                    frame = self.input_queue.get(timeout=0.05)  # 50ms max wait
                except queue.Empty:
                    continue
                
                # Skip if paused
                if self._state == NodeState.PAUSED:
                    self.input_queue.task_done()
                    continue
                
                # Process frame
                t0 = time.time()
                processed_frame = self._process(frame)
                latency_ms = (time.time() - t0) * 1000
                
                # Update metadata
                processed_frame.metadata["vision_latency_ms"] = latency_ms
                processed_frame.metadata["vision_node"] = self.name
                
                # Push to output queue (FORCE drop old if full)
                try:
                    self.output_queue.put_nowait(processed_frame)
                except queue.Full:
                    # Drop old display frame, always send newest
                    try:
                        self.output_queue.get_nowait()
                    except queue.Empty:
                        pass
                    self.output_queue.put_nowait(processed_frame)
                
                self._frames_processed += 1
                self._record_latency(latency_ms)
                self._update_fps()
                self.input_queue.task_done()
            
            except Exception as exc:
                self._on_error(exc)
    
    def _process(self, frame: Frame) -> Frame:
        """Apply vision processing (detection, etc)"""
        if self.detector_func:
            try:
                # Run custom detector
                result = self.detector_func(frame.data)
                frame.metadata["detection_result"] = result
            except Exception as exc:
                logger.error(f"[{self.name}] Detection failed: {exc}")
        
        return frame


# ══════════════════════════════════════════════════════════
# Node 3: Display/Stream Node
# ══════════════════════════════════════════════════════════

class DisplayNode(GraphNode):
    """
    Display and streaming node.
    Pulls processed frames and displays/streams at target FPS.
    Smooth 20fps output regardless of vision node speed.
    """
    
    def __init__(
        self,
        input_queue: queue.Queue,
        target_fps: int = 20,
        jpeg_quality: int = 85
    ):
        super().__init__("Display")
        self.input_queue = input_queue
        self.target_fps = target_fps
        self.jpeg_quality = jpeg_quality
        
        self._latest_frame: Optional[Frame] = None
        self._frame_callbacks = []
    
    def add_callback(self, callback: Callable[[Frame, bytes], None]) -> None:
        """Register callback for each displayed frame"""
        self._frame_callbacks.append(callback)
    
    def _run(self) -> None:
        """Display loop: pull frames and render"""
        frame_interval = 1.0 / self.target_fps
        next_frame_time = time.time()
        
        while not self._stop_event.is_set():
            # Rate limiting
            now = time.time()
            sleep_time = next_frame_time - now
            if sleep_time > 0:
                time.sleep(sleep_time)
            next_frame_time = time.time() + frame_interval
            
            try:
                # Try to get latest processed frame
                try:
                    self._latest_frame = self.input_queue.get_nowait()
                except queue.Empty:
                    pass  # Use last frame if no new one
                
                if self._latest_frame is None:
                    continue
                
                # Encode as JPEG
                t0 = time.time()
                ok, buf = cv2.imencode(
                    ".jpg",
                    self._latest_frame.data,
                    [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality,
                     cv2.IMWRITE_JPEG_PROGRESSIVE, 1]
                )
                encode_time = (time.time() - t0) * 1000
                
                if not ok:
                    continue
                
                jpeg_data = bytes(buf)
                
                # Calculate total latency
                total_latency = (now - self._latest_frame.timestamp) * 1000
                self._latest_frame.metadata["display_latency_ms"] = encode_time
                self._latest_frame.metadata["total_latency_ms"] = total_latency
                
                # Call registered callbacks (WebSocket broadcast, etc)
                for callback in self._frame_callbacks:
                    try:
                        callback(self._latest_frame, jpeg_data)
                    except Exception as exc:
                        logger.error(f"[{self.name}] Callback error: {exc}")
                
                self._frames_processed += 1
                self._record_latency(total_latency)
                self._update_fps()
            
            except Exception as exc:
                self._on_error(exc)
    
    def get_latest_jpeg(self) -> Optional[bytes]:
        """Get latest JPEG-encoded frame"""
        if self._latest_frame is None:
            return None
        
        ok, buf = cv2.imencode(
            ".jpg",
            self._latest_frame.data,
            [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality]
        )
        return bytes(buf) if ok else None


# ══════════════════════════════════════════════════════════
# Pipeline Orchestrator
# ══════════════════════════════════════════════════════════

class CameraPipeline:
    """
    Multi-node graph pipeline orchestrator.
    Manages all nodes and provides unified control interface.
    """
    
    def __init__(
        self,
        width: int = 640,
        height: int = 480,
        capture_fps: int = 30,
        display_fps: int = 20,
        detector_func: Optional[Callable] = None
    ):
        logger.info("Initializing camera graph pipeline...")
        
        # CRITICAL: Queue size=1 for ZERO latency
        # Always drop old frames - only process most recent
        self.capture_queue = queue.Queue(maxsize=1)  # Capture -> Vision
        self.display_queue = queue.Queue(maxsize=1)  # Vision -> Display
        
        # Create nodes
        self.capture_node = CaptureNode(
            output_queue=self.capture_queue,
            width=width,
            height=height,
            fps=capture_fps
        )
        
        self.vision_node = VisionNode(
            input_queue=self.capture_queue,
            output_queue=self.display_queue,
            detector_func=detector_func
        )
        
        self.display_node = DisplayNode(
            input_queue=self.display_queue,
            target_fps=display_fps
        )
        
        self._nodes = [self.capture_node, self.vision_node, self.display_node]
        logger.info("Pipeline initialized")
    
    def start(self) -> None:
        """Start all pipeline nodes"""
        logger.info("Starting pipeline...")
        for node in self._nodes:
            node.start()
        logger.info("Pipeline running")
    
    def stop(self) -> None:
        """Stop all pipeline nodes"""
        logger.info("Stopping pipeline...")
        for node in reversed(self._nodes):
            node.stop()
        logger.info("Pipeline stopped")
    
    def pause_vision(self) -> None:
        """Pause vision processing (keeps capture/display running)"""
        self.vision_node.pause()
    
    def resume_vision(self) -> None:
        """Resume vision processing"""
        self.vision_node.resume()
    
    def set_exposure_compensation(self, ev: float) -> None:
        """
        Adjust exposure compensation dynamically.
        
        Args:
            ev: Exposure value (-4.0 to +4.0)
                Negative = darker, Positive = brighter
                
        Use this to fix dark/black beans in real-time:
            pipeline.set_exposure_compensation(1.0)  # Brighten
            pipeline.set_exposure_compensation(0.5)  # Slightly brighter
            pipeline.set_exposure_compensation(0.0)  # Reset to neutral
        """
        if hasattr(self.capture_node, '_picam') and self.capture_node._picam:
            try:
                self.capture_node._picam.set_controls({"ExposureValue": ev})
                logger.info(f"Exposure compensation set to {ev}")
            except Exception as exc:
                logger.error(f"Failed to set exposure: {exc}")
    
    def set_awb_mode(self, mode_name: str) -> None:
        """
        Change white balance mode dynamically.
        
        Args:
            mode_name: One of:
                - "auto": Automatic
                - "incandescent": Tungsten/warm LED (2800K) - DEFAULT for coffee beans
                - "tungsten": Same as incandescent
                - "fluorescent": Cool white (4000K)
                - "indoor": General indoor
                - "daylight": Outdoor daylight (5500K)
                - "cloudy": Overcast (6500K)
        """
        from libcamera import controls
        
        mode_map = {
            "auto": controls.AwbModeEnum.Auto,
            "incandescent": controls.AwbModeEnum.Incandescent,
            "tungsten": controls.AwbModeEnum.Tungsten,
            "fluorescent": controls.AwbModeEnum.Fluorescent,
            "indoor": controls.AwbModeEnum.Indoor,
            "daylight": controls.AwbModeEnum.Daylight,
            "cloudy": controls.AwbModeEnum.Cloudy,
        }
        
        if mode_name not in mode_map:
            logger.error(f"Invalid AWB mode: {mode_name}. Valid: {list(mode_map.keys())}")
            return
        
        if hasattr(self.capture_node, '_picam') and self.capture_node._picam:
            try:
                self.capture_node._picam.set_controls({"AwbMode": mode_map[mode_name]})
                logger.info(f"AWB mode set to {mode_name}")
            except Exception as exc:
                logger.error(f"Failed to set AWB mode: {exc}")
    
    def get_metrics(self) -> dict:
        """Get metrics from all nodes"""
        return {
            node.name: node.metrics
            for node in self._nodes
        }
    
    def add_display_callback(self, callback: Callable) -> None:
        """Register callback for display frames"""
        self.display_node.add_callback(callback)


# ══════════════════════════════════════════════════════════
# Singleton Instance
# ══════════════════════════════════════════════════════════

_pipeline_instance: Optional[CameraPipeline] = None

def get_pipeline(
    width: int = 640,
    height: int = 480,
    capture_fps: int = 30,
    display_fps: int = 20,
    detector_func: Optional[Callable] = None
) -> CameraPipeline:
    """Get or create pipeline singleton"""
    global _pipeline_instance
    if _pipeline_instance is None:
        _pipeline_instance = CameraPipeline(
            width=width,
            height=height,
            capture_fps=capture_fps,
            display_fps=display_fps,
            detector_func=detector_func
        )
    return _pipeline_instance
