"""
Zero-Latency Streaming Routes for MJPEG & WebSocket

Endpoints:
- GET /stream/mjpeg: MJPEG video stream (BGR JPEG)
- WS /ws/stream: WebSocket annotated stream (RGB base64 JPEG)

Features:
- Sub-50ms latency
- Correct colors (RGB→BGR→RGB handled properly)
- Frame-dropping for zero-lag
- Separate threads for capture/inference/display
"""

from __future__ import annotations

import asyncio
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from backend.core.zero_latency_stream import (
    get_frame_producer,
    get_mjpeg_generator,
    get_ws_handler,
    start_streaming
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["streaming"])


# ══════════════════════════════════════════════════════════
# MJPEG Stream Endpoint
# ══════════════════════════════════════════════════════════

@router.get("/stream/mjpeg")
async def mjpeg_stream():
    """
    Zero-latency MJPEG video stream.
    
    Features:
    - BGR JPEG frames (correct colors)
    - Frame-dropping (maxsize=1 queue)
    - Sub-50ms latency
    
    Usage:
        <img src="http://pi_ip:8000/stream/mjpeg" />
    """
    # Ensure producer is running
    start_streaming()
    
    # Get MJPEG generator
    generator = get_mjpeg_generator()
    
    logger.info("MJPEG stream started")
    
    return StreamingResponse(
        generator.generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        }
    )


# ══════════════════════════════════════════════════════════
# WebSocket Annotated Stream Endpoint
# ══════════════════════════════════════════════════════════

@router.websocket("/ws/stream")
async def websocket_stream(websocket: WebSocket):
    """
    Zero-latency WebSocket stream with annotations.
    
    Features:
    - RGB base64 JPEG (correct colors for Canvas)
    - Optional detection annotations
    - Frame-dropping (maxsize=1 queue)
    - Sub-50ms latency
    
    Message format:
    {
        "type": "frame",
        "payload": {
            "data": "<base64-jpeg>",
            "frame_id": 12345,
            "timestamp": 1234567890.123,
            "detection": {...}  // optional
        }
    }
    """
    # Ensure producer is running
    start_streaming()
    
    # Get WebSocket handler
    # TODO: Pass bean_detector.detect if you want annotations
    ws_handler = get_ws_handler(detector_func=None)
    
    await websocket.accept()
    ws_handler.add_connection(websocket)
    
    logger.info("WebSocket stream client connected")
    
    try:
        # Keep connection alive
        while True:
            try:
                # Receive commands (optional)
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=30.0
                )
                # Handle commands here if needed
            except asyncio.TimeoutError:
                # Send ping
                await websocket.send_json({"type": "ping"})
    
    except WebSocketDisconnect:
        logger.info("WebSocket stream client disconnected")
    except Exception as exc:
        logger.error(f"WebSocket error: {exc}")
    finally:
        ws_handler.remove_connection(websocket)


# ══════════════════════════════════════════════════════════
# Stats Endpoint
# ══════════════════════════════════════════════════════════

@router.get("/stream/stats")
async def stream_stats():
    """Get streaming stats"""
    producer = get_frame_producer()
    
    return {
        "status": "ok",
        "producer": producer.stats,
    }
