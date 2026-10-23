"""
Integration between zero-latency streaming and bean detection.

Connects the streaming module to the existing bean detector
for annotated WebSocket output.
"""

from __future__ import annotations

import logging
import cv2
from typing import Optional

from backend.core import bean_detector
from backend.core.zero_latency_stream import (
    get_ws_handler,
    get_frame_producer,
    start_streaming
)

logger = logging.getLogger(__name__)


def detector_wrapper(bgr_frame) -> Optional[dict]:
    """
    Wrapper for bean_detector.detect that returns JSON-serializable dict.
    
    Args:
        bgr_frame: BGR numpy array
    
    Returns:
        {
            "beans": [
                {
                    "bbox": [x, y, w, h],
                    "grade": "grade1",
                    "confidence": 0.95
                },
                ...
            ],
            "count": 3,
            "processing_ms": 45.2
        }
    """
    try:
        import time
        t0 = time.time()
        
        # Run detector (expects BGR)
        beans = bean_detector.detect(bgr_frame)
        
        proc_time = (time.time() - t0) * 1000
        
        return {
            "beans": [
                {
                    "bbox": list(b.bbox),
                    "grade": b.grade,
                    "confidence": float(b.confidence),
                }
                for b in beans
            ],
            "count": len(beans),
            "processing_ms": round(proc_time, 1),
        }
    except Exception as exc:
        logger.error(f"Detector wrapper error: {exc}")
        return None


def init_streaming_with_detection():
    """
    Initialize streaming with detection enabled.
    
    Call this in main.py startup to connect detector to WebSocket stream.
    """
    logger.info("Initializing streaming with detection...")
    
    # Get WebSocket handler with detector
    ws_handler = get_ws_handler(detector_func=detector_wrapper)
    
    # Start frame producer
    start_streaming()
    
    logger.info("Streaming with detection initialized")
    
    return ws_handler


def annotate_frame_for_display(bgr_frame, detection_result: Optional[dict]):
    """
    Annotate BGR frame with detection results for display.
    
    Args:
        bgr_frame: BGR numpy array
        detection_result: Detection dict from detector_wrapper
    
    Returns:
        Annotated BGR frame
    """
    if detection_result is None or not detection_result.get("beans"):
        return bgr_frame
    
    annotated = bgr_frame.copy()
    
    for bean in detection_result["beans"]:
        x, y, w, h = bean["bbox"]
        grade = bean["grade"]
        confidence = bean["confidence"]
        
        # Keep a thin, neutral outline so the bean's color stays visible.
        color = (55, 145, 85)  # muted green in BGR
        
        # Draw bounding box
        cv2.rectangle(annotated, (x, y), (x+w, y+h), color, 1, cv2.LINE_AA)
        
        # Draw label
        label = f"{grade} {confidence:.0%}"
        cv2.putText(
            annotated,
            label,
            (x, y - 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            color,
            1,
            cv2.LINE_AA,
        )
    
    return annotated


# ══════════════════════════════════════════════════════════
# Background Task for Annotated Stream
# ══════════════════════════════════════════════════════════

async def start_annotated_broadcast_loop():
    """
    Start background task that broadcasts annotated frames.
    
    This runs the WebSocket handler's broadcast loop which:
    1. Gets latest frame from producer
    2. Runs detection
    3. Annotates frame
    4. Broadcasts to all connected clients
    """
    import asyncio
    
    ws_handler = get_ws_handler(detector_func=detector_wrapper)
    
    logger.info("Starting annotated broadcast loop...")
    
    # Run broadcast loop as background task
    asyncio.create_task(ws_handler.broadcast_loop())
    
    logger.info("Annotated broadcast loop started")
