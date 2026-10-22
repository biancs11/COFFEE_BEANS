#!/usr/bin/env python3
"""
Test script for concurrent graph pipeline.

Demonstrates:
1. Real-time 30fps capture with zero lag
2. Continuous autofocus (always sharp)
3. Independent vision processing (10-15fps)
4. Smooth 20fps display output
5. Full metrics monitoring

Usage:
    python3 test_graph_pipeline.py

Controls:
    q - quit
    p - pause/resume vision processing
    m - show metrics
    s - save current frame
    h - toggle heavy processing
"""

import cv2
import time
import numpy as np
import sys
from backend.core.camera_graph_pipeline import get_pipeline, Frame

# Heavy processing simulator
heavy_processing = False

def simulate_detection(frame: np.ndarray) -> dict:
    """
    Simulate heavy coffee bean detection.
    Replace with actual bean_detector.detect() in production.
    """
    global heavy_processing
    
    if not heavy_processing:
        return {"beans": [], "processing_ms": 0}
    
    t0 = time.time()
    
    # Simulate heavy CV workload
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (15, 15), 0)
    edges = cv2.Canny(blurred, 50, 150)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    # Find "beans" (any circular contours)
    beans = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < 100 or area > 5000:
            continue
        
        x, y, w, h = cv2.boundingRect(cnt)
        if w < 10 or h < 10:
            continue
        
        beans.append({
            "bbox": (x, y, w, h),
            "area": area,
            "grade": f"grade{(len(beans) % 4) + 1}"
        })
    
    proc_time = (time.time() - t0) * 1000
    
    return {
        "beans": beans,
        "processing_ms": proc_time
    }

def annotate_frame(frame: np.ndarray, detection_result: dict) -> np.ndarray:
    """Draw detection results on frame"""
    annotated = frame.copy()
    
    beans = detection_result.get("beans", [])
    for bean in beans:
        x, y, w, h = bean["bbox"]
        grade = bean["grade"]
        
        # Color by grade
        colors = {
            "grade1": (0, 255, 0),
            "grade2": (0, 255, 255),
            "grade3": (0, 165, 255),
            "grade4": (0, 0, 255),
        }
        color = colors.get(grade, (255, 255, 255))
        
        cv2.rectangle(annotated, (x, y), (x+w, y+h), color, 2)
        cv2.putText(
            annotated,
            grade,
            (x, y - 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            color,
            2
        )
    
    return annotated

def display_callback(frame: Frame, jpeg_data: bytes) -> None:
    """
    Callback for each displayed frame.
    This is where you'd send to WebSocket, save to disk, etc.
    """
    # Annotate frame with detection results
    detection_result = frame.metadata.get("detection_result", {})
    annotated = annotate_frame(frame.data, detection_result)
    
    # Overlay metrics
    y_pos = 30
    metrics_text = [
        f"Frame ID: {frame.frame_id}",
        f"Beans: {len(detection_result.get('beans', []))}",
        f"Vision: {frame.metadata.get('vision_latency_ms', 0):.1f}ms",
        f"Total: {frame.metadata.get('total_latency_ms', 0):.1f}ms",
        f"Heavy Processing: {'ON' if heavy_processing else 'OFF'}",
    ]
    
    for text in metrics_text:
        cv2.putText(
            annotated,
            text,
            (10, y_pos),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 0),
            2
        )
        y_pos += 30
    
    # Display
    cv2.imshow("Graph Pipeline Test", annotated)

def print_metrics(metrics: dict) -> None:
    """Print formatted metrics"""
    print("\n" + "="*60)
    print("PIPELINE METRICS")
    print("="*60)
    
    for node_name, node_metrics in metrics.items():
        print(f"\n[{node_name}]")
        print(f"  State:           {node_metrics.state}")
        print(f"  Frames:          {node_metrics.frames_processed}")
        print(f"  FPS:             {node_metrics.fps:.1f}")
        print(f"  Avg Latency:     {node_metrics.avg_latency_ms:.2f}ms")
        print(f"  Errors:          {node_metrics.errors}")
        if node_metrics.last_error:
            print(f"  Last Error:      {node_metrics.last_error}")
    
    print("="*60 + "\n")

def main():
    global heavy_processing
    
    print("╔═══════════════════════════════════════════════════════╗")
    print("║  Concurrent Multi-Node Graph Pipeline Test           ║")
    print("║  Real-Time Coffee Bean Scanner                       ║")
    print("╚═══════════════════════════════════════════════════════╝")
    print()
    print("Controls:")
    print("  q - quit")
    print("  p - pause/resume vision processing")
    print("  m - show metrics")
    print("  s - save current frame")
    print("  h - toggle heavy processing")
    print("  + - increase exposure (+0.2) [if too dark]")
    print("  - - decrease exposure (-0.2) [if too bright/glare]")
    print("  w - cycle AWB mode (incandescent/fluorescent/daylight)")
    print("  a - cycle AE constraint (highlight/normal/shadows)")
    print()
    
    # Initialize pipeline
    pipeline = get_pipeline(
        width=640,
        height=480,
        capture_fps=30,
        display_fps=20,
        detector_func=simulate_detection
    )
    
    # Register display callback
    pipeline.add_display_callback(display_callback)
    
    # Start pipeline
    pipeline.start()
    
    print("Pipeline started. Press keys for controls...")
    print()
    
    vision_paused = False
    frame_count = 0
    last_metrics_time = time.time()
    current_exposure = -0.5  # Default anti-glare setting
    awb_modes = ["incandescent", "fluorescent", "daylight"]
    current_awb_idx = 0
    ae_constraint_modes = ["highlight", "normal", "shadows"]
    current_ae_idx = 0  # Start with highlight (anti-glare)
    
    try:
        while True:
            # Handle keyboard input
            key = cv2.waitKey(1) & 0xFF
            
            if key == ord('q'):
                print("Quitting...")
                break
            
            elif key == ord('p'):
                if vision_paused:
                    pipeline.resume_vision()
                    vision_paused = False
                    print("✓ Vision processing RESUMED")
                else:
                    pipeline.pause_vision()
                    vision_paused = True
                    print("⏸ Vision processing PAUSED")
            
            elif key == ord('m'):
                metrics = pipeline.get_metrics()
                print_metrics(metrics)
            
            elif key == ord('s'):
                frame_count += 1
                filename = f"frame_{int(time.time())}_{frame_count}.jpg"
                jpeg = pipeline.display_node.get_latest_jpeg()
                if jpeg:
                    with open(filename, 'wb') as f:
                        f.write(jpeg)
                    print(f"✓ Saved frame: {filename}")
            
            elif key == ord('h'):
                heavy_processing = not heavy_processing
                status = "ON" if heavy_processing else "OFF"
                print(f"Heavy processing: {status}")
            
            elif key == ord('+') or key == ord('='):
                current_exposure = min(current_exposure + 0.2, 4.0)
                pipeline.set_exposure_compensation(current_exposure)
                print(f"Exposure: {current_exposure:+.1f}")
            
            elif key == ord('-') or key == ord('_'):
                current_exposure = max(current_exposure - 0.2, -4.0)
                pipeline.set_exposure_compensation(current_exposure)
                print(f"Exposure: {current_exposure:+.1f}")
            
            elif key == ord('w'):
                current_awb_idx = (current_awb_idx + 1) % len(awb_modes)
                mode = awb_modes[current_awb_idx]
                pipeline.set_awb_mode(mode)
                print(f"AWB mode: {mode}")
            
            elif key == ord('a'):
                current_ae_idx = (current_ae_idx + 1) % len(ae_constraint_modes)
                mode = ae_constraint_modes[current_ae_idx]
                pipeline.set_ae_constraint_mode(mode)
                print(f"AE constraint: {mode}")
            
            # Auto-print metrics every 10 seconds
            if time.time() - last_metrics_time >= 10:
                last_metrics_time = time.time()
                metrics = pipeline.get_metrics()
                print(f"\n[Auto-metrics] Capture: {metrics['Capture'].fps}fps | "
                      f"Vision: {metrics['Vision'].fps}fps | "
                      f"Display: {metrics['Display'].fps}fps")
    
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    
    finally:
        # Stop pipeline
        pipeline.stop()
        cv2.destroyAllWindows()
        
        # Final metrics
        print("\n" + "="*60)
        print("FINAL METRICS")
        print("="*60)
        metrics = pipeline.get_metrics()
        print_metrics(metrics)
        
        print("Pipeline test complete.")

if __name__ == "__main__":
    main()
