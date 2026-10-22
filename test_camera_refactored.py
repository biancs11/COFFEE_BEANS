#!/usr/bin/env python3
"""
Test script for refactored camera architecture.

Tests:
1. Camera starts and captures at target FPS
2. Frame queue stays fresh (no stale frames)
3. Heavy processing doesn't block camera stream
4. Real-time display is smooth (no lag)

Usage:
    python test_camera_refactored.py

Press 'q' to quit, 's' to show stats
"""

import cv2
import time
import numpy as np
from backend.core.camera_refactored import camera_manager_refactored

def simulate_heavy_processing(frame: np.ndarray) -> np.ndarray:
    """Simulate heavy CV processing (50-100ms)"""
    # Blur + edge detection (CPU intensive)
    blurred = cv2.GaussianBlur(frame, (15, 15), 0)
    edges = cv2.Canny(blurred, 50, 150)
    return cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR)

def main():
    print("Starting refactored camera test...")
    print("Controls:")
    print("  q - quit")
    print("  s - show stats")
    print("  h - toggle heavy processing")
    print()
    
    camera_manager_refactored.start()
    
    # Wait for camera to initialize
    timeout = time.time() + 10
    while not camera_manager_refactored.is_running:
        if time.time() > timeout:
            print("ERROR: Camera failed to start")
            return
        time.sleep(0.1)
    
    print(f"Camera running at {camera_manager_refactored.fps}fps")
    print()
    
    heavy_processing = False
    frame_count = 0
    display_fps = 0.0
    fps_timer = time.time()
    last_frame_number = 0
    
    try:
        while True:
            # Get frame for display (non-blocking - immediate)
            frame = camera_manager_refactored.get_frame()
            
            if frame is None:
                print("No frame available")
                time.sleep(0.01)
                continue
            
            # Simulate detection workload (pull from queue)
            detection_frame = camera_manager_refactored.get_frame_for_detection()
            if detection_frame is not None:
                # Check for dropped frames
                if last_frame_number > 0:
                    dropped = detection_frame.frame_number - last_frame_number - 1
                    if dropped > 0:
                        print(f"⚠ Dropped {dropped} frames (queue full - consumer too slow)")
                last_frame_number = detection_frame.frame_number
                
                # Heavy processing (optional)
                if heavy_processing:
                    t0 = time.time()
                    processed = simulate_heavy_processing(detection_frame.frame)
                    proc_time = (time.time() - t0) * 1000
                    print(f"Frame {detection_frame.frame_number}: processing took {proc_time:.1f}ms")
            
            # Display frame
            display = frame.copy()
            
            # Calculate display FPS
            frame_count += 1
            elapsed = time.time() - fps_timer
            if elapsed >= 1.0:
                display_fps = frame_count / elapsed
                frame_count = 0
                fps_timer = time.time()
            
            # Overlay stats
            stats = camera_manager_refactored.stats
            cv2.putText(
                display,
                f"Camera FPS: {stats['fps']:.1f}",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2
            )
            cv2.putText(
                display,
                f"Display FPS: {display_fps:.1f}",
                (10, 60),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2
            )
            cv2.putText(
                display,
                f"Queue: {stats['queue_size']}/2",
                (10, 90),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 255),
                2
            )
            cv2.putText(
                display,
                f"Heavy processing: {'ON' if heavy_processing else 'OFF'}",
                (10, 120),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 0, 255) if heavy_processing else (128, 128, 128),
                2
            )
            
            cv2.imshow("Camera Test (Refactored)", display)
            
            # Handle keys
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('s'):
                print("\n=== Camera Stats ===")
                for k, v in stats.items():
                    print(f"  {k}: {v}")
                print()
            elif key == ord('h'):
                heavy_processing = not heavy_processing
                print(f"Heavy processing: {'ON' if heavy_processing else 'OFF'}")
    
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    finally:
        camera_manager_refactored.stop()
        cv2.destroyAllWindows()
        print("Camera stopped")

if __name__ == "__main__":
    main()
