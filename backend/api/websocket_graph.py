"""
WebSocket integration with graph pipeline.

Connects the concurrent multi-node graph pipeline to FastAPI WebSocket.
Provides real-time video stream and detection events to connected clients.
"""

from __future__ import annotations
import asyncio
import base64
import json
import logging
from typing import Optional

from fastapi import WebSocket, WebSocketDisconnect

from ..core.camera_graph_pipeline import get_pipeline, Frame
from ..core import app_state, bean_detector, SystemStatus
from ..core.config import settings

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════
# WebSocket Connection Manager
# ══════════════════════════════════════════════════════════

class WebSocketManager:
    """Manages WebSocket connections and broadcasting"""
    
    def __init__(self):
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self._max_connections = getattr(settings, "WS_MAX_CONNECTIONS", 10)
    
    async def connect(self, websocket: WebSocket) -> bool:
        """Add new WebSocket connection"""
        async with self._lock:
            if len(self._connections) >= self._max_connections:
                return False
            self._connections.add(websocket)
            logger.info(f"WS connected - total: {len(self._connections)}")
            return True
    
    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove WebSocket connection"""
        async with self._lock:
            self._connections.discard(websocket)
            logger.info(f"WS disconnected - remaining: {len(self._connections)}")
    
    async def broadcast(self, message: dict) -> None:
        """Broadcast message to all connected clients"""
        if not self._connections:
            return
        
        async with self._lock:
            dead = set()
            for ws in self._connections:
                try:
                    await ws.send_json(message)
                except Exception:
                    dead.add(ws)
            
            for ws in dead:
                self._connections.discard(ws)


ws_manager = WebSocketManager()


# ══════════════════════════════════════════════════════════
# Pipeline Frame Callback
# ══════════════════════════════════════════════════════════

async def _broadcast_frame_async(frame: Frame, jpeg_data: bytes):
    """
    Async callback for pipeline frames.
    Broadcasts frame and detection data to WebSocket clients.
    """
    try:
        # Prepare frame message
        frame_msg = {
            "type": "frame",
            "payload": {
                "data": base64.b64encode(jpeg_data).decode(),
                "frame_id": frame.frame_id,
                "timestamp": frame.timestamp,
                "fps": frame.metadata.get("capture_fps", 0),
            }
        }
        
        # Broadcast frame
        await ws_manager.broadcast(frame_msg)
        
        # If detection result exists, broadcast separately
        detection_result = frame.metadata.get("detection_result", {})
        beans = detection_result.get("beans", [])
        
        if beans:
            detection_msg = {
                "type": "detection",
                "payload": {
                    "frame_id": frame.frame_id,
                    "timestamp": frame.timestamp,
                    "beans": beans,
                    "processing_ms": detection_result.get("processing_ms", 0),
                    "latency_ms": frame.metadata.get("total_latency_ms", 0),
                }
            }
            await ws_manager.broadcast(detection_msg)
    
    except Exception as exc:
        logger.error(f"Frame broadcast error: {exc}")


# Synchronous wrapper for pipeline callback
def pipeline_frame_callback(frame: Frame, jpeg_data: bytes):
    """
    Synchronous callback that schedules async broadcast.
    Called by display node in graph pipeline.
    """
    try:
        loop = asyncio.get_event_loop()
        asyncio.run_coroutine_threadsafe(
            _broadcast_frame_async(frame, jpeg_data),
            loop
        )
    except Exception as exc:
        logger.error(f"Callback scheduling error: {exc}")


# ══════════════════════════════════════════════════════════
# Background Stats Loop
# ══════════════════════════════════════════════════════════

async def stats_background_loop(pipeline):
    """
    Background task that broadcasts system stats periodically.
    Runs independently of frame pipeline.
    """
    logger.info("Stats loop started")
    
    try:
        while True:
            await asyncio.sleep(1.0)  # 1Hz stats
            
            # Get pipeline metrics
            metrics = pipeline.get_metrics()
            
            # Prepare stats message
            stats_msg = {
                "type": "stats",
                "payload": {
                    "status": app_state.status.value,
                    "uptime_seconds": app_state.uptime_seconds,
                    "beans_processed": app_state.sort_counts.total,
                    "sort_counts": {
                        "grade1": app_state.sort_counts.grade1,
                        "grade2": app_state.sort_counts.grade2,
                        "grade3": app_state.sort_counts.grade3,
                        "grade4": app_state.sort_counts.grade4,
                    },
                    "camera_fps": metrics["Capture"].fps,
                    "vision_fps": metrics["Vision"].fps,
                    "display_fps": metrics["Display"].fps,
                    "avg_latency_ms": metrics["Display"].avg_latency_ms,
                    "pipeline_state": {
                        "capture": metrics["Capture"].state,
                        "vision": metrics["Vision"].state,
                        "display": metrics["Display"].state,
                    },
                }
            }
            
            await ws_manager.broadcast(stats_msg)
    
    except asyncio.CancelledError:
        logger.info("Stats loop cancelled")


# ══════════════════════════════════════════════════════════
# Pipeline Initialization
# ══════════════════════════════════════════════════════════

def init_graph_pipeline():
    """
    Initialize graph pipeline with bean detector.
    Call this on application startup.
    """
    logger.info("Initializing graph pipeline...")
    
    # Define detection function
    def detect_beans(frame):
        """Wrapper for bean detector"""
        try:
            beans = bean_detector.detect(frame)
            return {
                "beans": [
                    {
                        "bbox": b.bbox,
                        "grade": b.grade,
                        "confidence": b.confidence,
                    }
                    for b in beans
                ],
                "processing_ms": 0,  # detector tracks this internally
            }
        except Exception as exc:
            logger.error(f"Bean detection failed: {exc}")
            return {"beans": [], "processing_ms": 0}
    
    # Create pipeline
    pipeline = get_pipeline(
        width=getattr(settings, "CAMERA_WIDTH", 640),
        height=getattr(settings, "CAMERA_HEIGHT", 480),
        capture_fps=getattr(settings, "CAMERA_FPS", 30),
        display_fps=20,
        detector_func=detect_beans
    )
    
    # Register frame callback
    pipeline.add_display_callback(pipeline_frame_callback)
    
    # Start pipeline
    pipeline.start()
    
    logger.info("Graph pipeline initialized and started")
    return pipeline


# ══════════════════════════════════════════════════════════
# WebSocket Endpoint
# ══════════════════════════════════════════════════════════

async def websocket_endpoint_graph(websocket: WebSocket):
    """
    WebSocket endpoint using graph pipeline.
    Ultra-low latency, smooth video, real-time detection.
    """
    if not await ws_manager.connect(websocket):
        await websocket.close(code=1008, reason="Too many connections")
        return
    
    try:
        await websocket.accept()
        await websocket.send_json({
            "type": "connected",
            "payload": {
                "message": "Connected to graph pipeline",
                "latency": "< 50ms",
            },
        })
        
        # Keep connection alive and handle commands
        while True:
            try:
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=30.0
                )
                
                # Handle commands
                try:
                    msg = json.loads(data)
                    command = msg.get("command")
                    
                    if command == "pause_vision":
                        pipeline = get_pipeline()
                        pipeline.pause_vision()
                        await websocket.send_json({
                            "type": "ack",
                            "payload": {"command": "pause_vision", "status": "ok"}
                        })
                    
                    elif command == "resume_vision":
                        pipeline = get_pipeline()
                        pipeline.resume_vision()
                        await websocket.send_json({
                            "type": "ack",
                            "payload": {"command": "resume_vision", "status": "ok"}
                        })
                    
                    elif command == "get_metrics":
                        pipeline = get_pipeline()
                        metrics = pipeline.get_metrics()
                        await websocket.send_json({
                            "type": "metrics",
                            "payload": {
                                node: {
                                    "state": m.state,
                                    "fps": m.fps,
                                    "latency_ms": m.avg_latency_ms,
                                }
                                for node, m in metrics.items()
                            }
                        })
                    
                    elif command == "set_exposure":
                        # Adjust exposure: {"command": "set_exposure", "value": 1.0}
                        ev = msg.get("value", 0.8)
                        pipeline = get_pipeline()
                        pipeline.set_exposure_compensation(ev)
                        await websocket.send_json({
                            "type": "ack",
                            "payload": {"command": "set_exposure", "value": ev, "status": "ok"}
                        })
                    
                    elif command == "set_awb":
                        # Change AWB mode: {"command": "set_awb", "mode": "incandescent"}
                        mode = msg.get("mode", "incandescent")
                        pipeline = get_pipeline()
                        pipeline.set_awb_mode(mode)
                        await websocket.send_json({
                            "type": "ack",
                            "payload": {"command": "set_awb", "mode": mode, "status": "ok"}
                        })
                    
                    elif command == "set_ae_constraint":
                        # Change AE constraint: {"command": "set_ae_constraint", "mode": "highlight"}
                        mode = msg.get("mode", "highlight")
                        pipeline = get_pipeline()
                        pipeline.set_ae_constraint_mode(mode)
                        await websocket.send_json({
                            "type": "ack",
                            "payload": {"command": "set_ae_constraint", "mode": mode, "status": "ok"}
                        })
                
                except json.JSONDecodeError:
                    pass
            
            except asyncio.TimeoutError:
                # Send ping
                await websocket.send_json({"type": "ping"})
    
    except WebSocketDisconnect:
        logger.info("Client disconnected")
    except Exception as exc:
        logger.error(f"WebSocket error: {exc}")
    finally:
        await ws_manager.disconnect(websocket)
