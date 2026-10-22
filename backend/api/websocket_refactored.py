"""
WebSocket with Producer-Consumer Frame Processing

Architecture:
  - Camera producer: 30fps continuous capture (runs in camera thread)
  - Frame broadcaster: 20fps JPEG stream (lightweight, asyncio)
  - Detection consumer: 10-15fps heavy CV processing (separate thread pool)
  
This decouples:
  - Camera grab (never blocks)
  - Stream display (smooth 20fps, no lag)
  - Bean detection (runs at its own pace, doesn't freeze stream)
"""

from __future__ import annotations
import asyncio
import base64
import concurrent.futures
import logging
import time
from typing import Optional

from fastapi import WebSocket, WebSocketDisconnect

from ..core import (
    app_state, bean_detector,
    sorting_controller, SystemStatus,
)
from ..core.camera_refactored import camera_manager_refactored
from ..core.config import settings

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════
# WebSocket Connection Manager
# ══════════════════════════════════════════════════════════

class WebSocketManager:
    def __init__(self):
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self._max_connections = getattr(settings, "WS_MAX_CONNECTIONS", 10)

    async def connect(self, websocket: WebSocket) -> bool:
        async with self._lock:
            if len(self._connections) >= self._max_connections:
                return False
            self._connections.add(websocket)
            logger.info(f"WS connected - total: {len(self._connections)}")
            return True

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(websocket)
            logger.info(f"WS disconnected - remaining: {len(self._connections)}")

    async def broadcast(self, message: dict) -> None:
        if not self._connections:
            return
        
        data = str.encode(str(message)) if not isinstance(message, str) else message.encode()
        
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
# Detection Worker (Runs in Thread Pool)
# ══════════════════════════════════════════════════════════

def _detect_beans_blocking(frame, frame_number: int):
    """
    Heavy detection workload - runs in thread pool.
    Returns: (beans, annotated_frame, processing_time_ms)
    """
    import cv2
    t0 = time.time()
    
    try:
        beans = bean_detector.detect(frame)
        
        # Draw annotations
        annotated = frame.copy()
        for bean in beans:
            x, y, w, h = bean.bbox
            color = {
                "grade1": (0, 255, 0),    # green
                "grade2": (0, 255, 255),  # yellow
                "grade3": (0, 165, 255),  # orange
                "grade4": (0, 0, 255),    # red
            }.get(bean.grade, (255, 255, 255))
            
            cv2.rectangle(annotated, (x, y), (x+w, y+h), color, 2)
            cv2.putText(
                annotated,
                f"{bean.grade} {bean.confidence:.0%}",
                (x, y - 5),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                color,
                2
            )
        
        proc_ms = (time.time() - t0) * 1000
        return beans, annotated, proc_ms
    
    except Exception as exc:
        logger.error(f"Detection failed: {exc}")
        return [], frame, 0.0


# ══════════════════════════════════════════════════════════
# Background Detection Loop
# ══════════════════════════════════════════════════════════

async def detection_background_loop():
    """
    Consumer: pulls frames from camera queue and processes them.
    Runs detection in thread pool so it never blocks the asyncio loop.
    """
    logger.info("Detection background loop started")
    
    loop = asyncio.get_running_loop()
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="detect")
    
    last_stats_time = 0.0
    last_frame_broadcast = 0.0
    frame_count = 0
    
    try:
        while True:
            await asyncio.sleep(0.005)  # 5ms check interval
            
            now = time.time()
            
            # ── PAUSED: just broadcast raw frames ─────────────
            if app_state.status == SystemStatus.PAUSED:
                if now - last_frame_broadcast >= 0.05:  # 20fps
                    last_frame_broadcast = now
                    frame = camera_manager_refactored.get_frame()
                    if frame:
                        try:
                            jpeg = camera_manager_refactored.get_jpeg(quality=85)
                            if jpeg:
                                await ws_manager.broadcast({
                                    "type": "frame",
                                    "payload": {
                                        "data": base64.b64encode(jpeg).decode(),
                                        "fps": camera_manager_refactored.fps,
                                        "paused": True,
                                    },
                                })
                        except Exception as exc:
                            logger.debug(f"Frame broadcast error: {exc}")
                
                # Stats broadcast
                if now - last_stats_time >= 1.0:
                    last_stats_time = now
                    await ws_manager.broadcast({
                        "type": "stats",
                        "payload": {
                            "status": app_state.status.value,
                            "camera_fps": camera_manager_refactored.fps,
                            "camera_state": camera_manager_refactored.state.value,
                        },
                    })
                continue
            
            # ── RUNNING: detection + sorting ──────────────────
            if app_state.status != SystemStatus.RUNNING:
                continue
            
            # Get frame from queue (non-blocking)
            camera_frame = camera_manager_refactored.get_frame_for_detection()
            if camera_frame is None:
                # No new frame ready - broadcast last frame for smooth stream
                if now - last_frame_broadcast >= 0.05:  # 20fps
                    last_frame_broadcast = now
                    jpeg = camera_manager_refactored.get_jpeg(quality=85)
                    if jpeg:
                        await ws_manager.broadcast({
                            "type": "frame",
                            "payload": {
                                "data": base64.b64encode(jpeg).decode(),
                                "fps": camera_manager_refactored.fps,
                            },
                        })
                continue
            
            frame_count += 1
            frame = camera_frame.frame
            
            # Quick pre-check: skip empty frames
            if not bean_detector.has_beans_quick(frame):
                # No beans - broadcast raw frame
                if now - last_frame_broadcast >= 0.05:  # 20fps
                    last_frame_broadcast = now
                    try:
                        import cv2
                        ok, buf = cv2.imencode(
                            ".jpg", frame,
                            [cv2.IMWRITE_JPEG_QUALITY, 85]
                        )
                        if ok:
                            await ws_manager.broadcast({
                                "type": "frame",
                                "payload": {
                                    "data": base64.b64encode(bytes(buf)).decode(),
                                    "fps": camera_manager_refactored.fps,
                                },
                            })
                    except Exception:
                        pass
                continue
            
            # Heavy detection - run in thread pool (non-blocking)
            try:
                beans, annotated, proc_ms = await loop.run_in_executor(
                    executor,
                    _detect_beans_blocking,
                    frame,
                    camera_frame.frame_number
                )
                
                logger.info(f"Frame {camera_frame.frame_number}: {len(beans)} beans, {proc_ms:.1f}ms")
                
                # Trigger sorting actions
                for bean in beans:
                    app_state.sort_counts.increment(bean.grade)
                    # TODO: sorting_controller.eject(bean.grade, bean.bbox)
                
                # Broadcast annotated frame
                if now - last_frame_broadcast >= 0.05:  # 20fps
                    last_frame_broadcast = now
                    try:
                        import cv2
                        ok, buf = cv2.imencode(
                            ".jpg", annotated,
                            [cv2.IMWRITE_JPEG_QUALITY, 85]
                        )
                        if ok:
                            await ws_manager.broadcast({
                                "type": "frame",
                                "payload": {
                                    "data": base64.b64encode(bytes(buf)).decode(),
                                    "fps": camera_manager_refactored.fps,
                                    "beans": len(beans),
                                },
                            })
                    except Exception:
                        pass
                
                # Broadcast detection event
                await ws_manager.broadcast({
                    "type": "detection",
                    "payload": {
                        "frame_number": camera_frame.frame_number,
                        "timestamp": camera_frame.timestamp,
                        "beans": [
                            {
                                "grade": b.grade,
                                "confidence": round(b.confidence, 3),
                                "bbox": b.bbox,
                            }
                            for b in beans
                        ],
                        "processing_ms": round(proc_ms, 1),
                    },
                })
            
            except Exception as exc:
                logger.error(f"Detection processing failed: {exc}", exc_info=True)
            
            # Stats broadcast
            if now - last_stats_time >= 1.0:
                last_stats_time = now
                await ws_manager.broadcast({
                    "type": "stats",
                    "payload": {
                        "status": app_state.status.value,
                        "beans_processed": app_state.sort_counts.total,
                        "camera_fps": camera_manager_refactored.fps,
                        "camera_state": camera_manager_refactored.state.value,
                        "sort_counts": {
                            "grade1": app_state.sort_counts.grade1,
                            "grade2": app_state.sort_counts.grade2,
                            "grade3": app_state.sort_counts.grade3,
                            "grade4": app_state.sort_counts.grade4,
                        },
                    },
                })
    
    except asyncio.CancelledError:
        logger.info("Detection loop cancelled")
    finally:
        executor.shutdown(wait=False)
        logger.info("Detection loop stopped")


# ══════════════════════════════════════════════════════════
# WebSocket Endpoint
# ══════════════════════════════════════════════════════════

async def websocket_endpoint_refactored(websocket: WebSocket):
    """WebSocket endpoint with refactored camera architecture"""
    if not await ws_manager.connect(websocket):
        await websocket.close(code=1008, reason="Too many connections")
        return
    
    try:
        await websocket.accept()
        await websocket.send_json({
            "type": "connected",
            "payload": {"message": "WebSocket connected (refactored)"},
        })
        
        # Keep connection alive
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                # Handle commands if needed
            except asyncio.TimeoutError:
                # Send ping
                await websocket.send_json({"type": "ping"})
    
    except WebSocketDisconnect:
        logger.info("Client disconnected")
    except Exception as exc:
        logger.error(f"WebSocket error: {exc}")
    finally:
        await ws_manager.disconnect(websocket)
