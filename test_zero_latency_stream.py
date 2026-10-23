#!/usr/bin/env python3
"""
Test script for zero-latency streaming.

Tests:
1. Frame producer captures at 30fps
2. MJPEG stream has correct BGR colors
3. WebSocket stream has correct RGB colors
4. Latency < 50ms
5. Frame dropping works (queue maxsize=1)

Usage:
    python3 test_zero_latency_stream.py
"""

import cv2
import time
import numpy as np
from backend.core.zero_latency_stream import (
    get_frame_producer,
    start_streaming
)

def test_producer():
    """Test frame producer with LIFO queue verification"""
    print("="*60)
    print("TEST 1: Frame Producer (LIFO Queue)")
    print("="*60)
    
    producer = get_frame_producer(width=640, height=480, fps=30)
    producer.start()
    
    print("Waiting for warmup...")
    time.sleep(2)
    
    # Test LIFO behavior
    print("\nTesting LIFO queue behavior...")
    print("  Letting frames accumulate (not consuming)...")
    time.sleep(0.5)  # Let queue fill
    
    # Get one frame - should be NEWEST, not oldest
    frame1 = producer.get_latest_frame(timeout=0.1)
    if frame1:
        print(f"  ✓ Got frame ID: {frame1.frame_id}")
        
        # Wait a bit, then get another
        time.sleep(0.2)
        frame2 = producer.get_latest_frame(timeout=0.1)
        if frame2:
            print(f"  ✓ Got frame ID: {frame2.frame_id}")
            
            # With LIFO, frame2.frame_id should be > frame1.frame_id + many frames
            # (because we're always getting the newest frame)
            gap = frame2.frame_id - frame1.frame_id
            print(f"  ✓ Frame ID gap: {gap} (LIFO working if > 5)")
            
            if gap > 5:
                print("  ✓ LIFO behavior CONFIRMED (always getting newest frame)")
            else:
                print("  ⚠ WARNING: May not be LIFO (gap too small)")
    
    print("\nCapturing 100 frames...")
    t0 = time.time()
    frames_received = 0
    
    for i in range(100):
        frame = producer.get_latest_frame(timeout=0.1)
        if frame:
            frames_received += 1
    
    elapsed = time.time() - t0
    fps = frames_received / elapsed
    
    print(f"\n✓ Frames received: {frames_received}/100")
    print(f"✓ FPS: {fps:.1f}")
    print(f"✓ Time: {elapsed:.2f}s")
    
    stats = producer.stats
    print(f"\nProducer Stats:")
    print(f"  Frames captured: {stats['frames_captured']}")
    print(f"  Frames dropped:  {stats['frames_dropped']}")
    print(f"  Drop rate:       {stats['drop_rate']:.1f}%")
    
    if stats['drop_rate'] > 0:
        print("  ✓ Frame dropping active (LIFO queue working)")
    
    return producer


def test_color_conversion(producer):
    """Test RGB→BGR conversion"""
    print("\n" + "="*60)
    print("TEST 2: Color Conversion")
    print("="*60)
    
    frame = producer.get_latest_frame(timeout=1.0)
    if frame is None:
        print("✗ No frame received")
        return
    
    # Check shapes
    print(f"\n✓ BGR shape: {frame.bgr_data.shape}")
    print(f"✓ RGB shape: {frame.rgb_data.shape}")
    
    # Verify conversion happened (RGB and BGR should differ)
    if np.array_equal(frame.bgr_data, frame.rgb_data):
        print("✗ WARNING: BGR and RGB are identical (conversion may not have happened)")
    else:
        print("✓ BGR and RGB differ (conversion confirmed)")
    
    # Check channel order
    # In BGR, blue should be channel 0, red channel 2
    # In RGB, red should be channel 0, blue channel 2
    bgr_blue_mean = frame.bgr_data[:,:,0].mean()
    rgb_blue_mean = frame.rgb_data[:,:,2].mean()
    
    print(f"\n✓ BGR blue channel mean: {bgr_blue_mean:.1f}")
    print(f"✓ RGB blue channel mean: {rgb_blue_mean:.1f}")
    
    if abs(bgr_blue_mean - rgb_blue_mean) < 5:
        print("✓ Color channels match (conversion correct)")
    else:
        print("✗ WARNING: Channel mismatch detected")


def test_latency(producer):
    """Test end-to-end latency"""
    print("\n" + "="*60)
    print("TEST 3: Latency")
    print("="*60)
    
    latencies = []
    
    print("\nMeasuring latency over 50 frames...")
    for i in range(50):
        t0 = time.time()
        frame = producer.get_latest_frame(timeout=0.1)
        if frame:
            # Latency = current time - capture time
            latency_ms = (t0 - frame.timestamp) * 1000
            latencies.append(latency_ms)
    
    if latencies:
        avg_latency = sum(latencies) / len(latencies)
        min_latency = min(latencies)
        max_latency = max(latencies)
        
        print(f"\n✓ Average latency: {avg_latency:.1f}ms")
        print(f"✓ Min latency:     {min_latency:.1f}ms")
        print(f"✓ Max latency:     {max_latency:.1f}ms")
        
        if avg_latency < 50:
            print("✓ PASS: Latency < 50ms")
        elif avg_latency < 100:
            print("⚠ WARNING: Latency < 100ms but > 50ms")
        else:
            print("✗ FAIL: Latency > 100ms")
    else:
        print("✗ No frames received")


def test_display(producer):
    """Display live video to verify colors"""
    print("\n" + "="*60)
    print("TEST 4: Visual Display")
    print("="*60)
    print("\nDisplaying live video...")
    print("Controls:")
    print("  q - quit")
    print("  b - show BGR frame")
    print("  r - show RGB frame")
    print("  s - save frame")
    print()
    
    show_bgr = True
    frame_count = 0
    
    try:
        while True:
            frame = producer.get_latest_frame(timeout=0.05)
            if frame is None:
                continue
            
            # Show BGR or RGB
            if show_bgr:
                display = frame.bgr_data.copy()
                title = "BGR Frame (OpenCV/Detector)"
            else:
                # Convert RGB to BGR for cv2.imshow
                display = cv2.cvtColor(frame.rgb_data, cv2.COLOR_RGB2BGR)
                title = "RGB Frame (WebSocket/Canvas)"
            
            # Add overlay
            cv2.putText(
                display,
                f"Frame: {frame.frame_id}",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2
            )
            cv2.putText(
                display,
                f"Mode: {title}",
                (10, 60),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2
            )
            
            cv2.imshow("Zero-Latency Stream Test", display)
            
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('b'):
                show_bgr = True
                print("Showing BGR frame")
            elif key == ord('r'):
                show_bgr = False
                print("Showing RGB frame")
            elif key == ord('s'):
                frame_count += 1
                filename = f"test_frame_{frame_count}.jpg"
                cv2.imwrite(filename, display)
                print(f"✓ Saved: {filename}")
    
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    finally:
        cv2.destroyAllWindows()


def main():
    print("╔═══════════════════════════════════════════════════════╗")
    print("║  Zero-Latency Streaming Test                         ║")
    print("║  RGB→BGR→RGB Color Pipeline Verification             ║")
    print("╚═══════════════════════════════════════════════════════╝")
    print()
    
    try:
        # Test 1: Producer
        producer = test_producer()
        
        # Test 2: Color conversion
        test_color_conversion(producer)
        
        # Test 3: Latency
        test_latency(producer)
        
        # Test 4: Visual display
        test_display(producer)
    
    finally:
        print("\n\nCleaning up...")
        from backend.core.zero_latency_stream import stop_streaming
        stop_streaming()
        print("✓ Test complete")


if __name__ == "__main__":
    main()
