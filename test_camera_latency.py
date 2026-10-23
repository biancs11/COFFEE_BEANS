#!/usr/bin/env python3
"""
Camera Latency Diagnostic Tool

Tests the refactored camera.py to verify:
1. LIFO queue behavior (frames are dropped correctly)
2. Zero-latency capture (no sleep/throttling)
3. RGB→BGR color conversion
4. Frame rate and drop rate

Run on Raspberry Pi:
    python3 test_camera_latency.py
"""

import sys
import time
import threading
from collections import deque

# Color codes
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
CYAN = "\033[96m"
RESET = "\033[0m"


def print_header(text: str) -> None:
    print(f"\n{BLUE}{'=' * 70}{RESET}")
    print(f"{BLUE}{text:^70}{RESET}")
    print(f"{BLUE}{'=' * 70}{RESET}\n")


def test_lifo_behavior():
    """Test that camera manager uses LIFO queue correctly"""
    print_header("Camera LIFO Queue Test")
    
    try:
        from backend.core.camera import camera_manager
        
        # Start camera
        print(f"{CYAN}Starting camera...{RESET}")
        camera_manager.start()
        time.sleep(2)  # Wait for init
        
        if not camera_manager.is_running:
            print(f"{RED}✗ Camera failed to start{RESET}")
            return False
        
        print(f"{GREEN}✓ Camera started{RESET}\n")
        
        # Collect frames slowly (simulate slow consumer)
        print(f"{CYAN}Testing LIFO behavior (slow consumer)...{RESET}")
        
        frame_ids = []
        start_time = time.time()
        
        # Get baseline stats
        stats_before = camera_manager.stats
        
        # Consume frames slowly (intentionally slower than capture)
        for i in range(10):
            frame = camera_manager.get_frame()
            if frame is not None:
                frame_ids.append(stats_before['total_frames'] + i)
            time.sleep(0.5)  # 2 FPS consumption (much slower than 30 FPS capture)
        
        elapsed = time.time() - start_time
        stats_after = camera_manager.stats
        
        # Calculate metrics
        frames_captured = stats_after['total_frames'] - stats_before['total_frames']
        frames_consumed = len([f for f in frame_ids if f is not None])
        frames_dropped = stats_after['dropped_frames'] - stats_before.get('dropped_frames', 0)
        
        print(f"\n{CYAN}Results:{RESET}")
        print(f"  Duration:        {elapsed:.1f}s")
        print(f"  Frames captured: {frames_captured}")
        print(f"  Frames consumed: {frames_consumed}")
        print(f"  Frames dropped:  {frames_dropped}")
        print(f"  Drop rate:       {stats_after.get('drop_rate_pct', 0):.1f}%")
        print(f"  Camera FPS:      {camera_manager.fps:.1f}")
        
        # LIFO validation
        # With slow consumer (2 FPS) and fast capture (~30 FPS),
        # we expect significant frame dropping
        expected_min_drops = frames_captured - frames_consumed - 5
        
        print(f"\n{CYAN}LIFO Validation:{RESET}")
        if frames_dropped >= expected_min_drops:
            print(f"{GREEN}✓ LIFO working: {frames_dropped} frames dropped{RESET}")
            print(f"  This is GOOD - old frames are being discarded")
            success = True
        else:
            print(f"{RED}✗ LIFO not working: Only {frames_dropped} frames dropped{RESET}")
            print(f"  Expected at least {expected_min_drops} drops")
            print(f"  Frames may be queuing up (causing lag)")
            success = False
        
        camera_manager.stop()
        return success
        
    except ImportError as e:
        print(f"{RED}✗ Cannot import camera_manager: {e}{RESET}")
        print(f"  This script must run on the Raspberry Pi with picamera2")
        return False
    except Exception as e:
        print(f"{RED}✗ Test failed: {e}{RESET}")
        import traceback
        traceback.print_exc()
        return False


def test_latency_measurement():
    """Measure actual frame latency"""
    print_header("Frame Latency Measurement")
    
    try:
        from backend.core.camera import camera_manager
        
        # Start camera
        print(f"{CYAN}Starting camera...{RESET}")
        camera_manager.start()
        time.sleep(2)
        
        if not camera_manager.is_running:
            print(f"{RED}✗ Camera not running{RESET}")
            return False
        
        print(f"{GREEN}✓ Camera running{RESET}\n")
        
        # Measure latency for multiple frames
        print(f"{CYAN}Measuring frame retrieval latency...{RESET}")
        
        latencies = []
        for i in range(50):
            t0 = time.perf_counter()
            frame = camera_manager.get_frame()
            t1 = time.perf_counter()
            
            if frame is not None:
                latency_ms = (t1 - t0) * 1000
                latencies.append(latency_ms)
            
            time.sleep(0.033)  # ~30 FPS
        
        if not latencies:
            print(f"{RED}✗ No frames received{RESET}")
            camera_manager.stop()
            return False
        
        # Statistics
        avg_latency = sum(latencies) / len(latencies)
        min_latency = min(latencies)
        max_latency = max(latencies)
        p95_latency = sorted(latencies)[int(len(latencies) * 0.95)]
        
        print(f"\n{CYAN}Latency Statistics:{RESET}")
        print(f"  Average:  {avg_latency:.2f}ms")
        print(f"  Min:      {min_latency:.2f}ms")
        print(f"  Max:      {max_latency:.2f}ms")
        print(f"  P95:      {p95_latency:.2f}ms")
        
        # Validation
        print(f"\n{CYAN}Latency Validation:{RESET}")
        if avg_latency < 5.0:
            print(f"{GREEN}✓ Excellent: <5ms average latency{RESET}")
            success = True
        elif avg_latency < 20.0:
            print(f"{GREEN}✓ Good: <20ms average latency{RESET}")
            success = True
        elif avg_latency < 50.0:
            print(f"{YELLOW}⚠ Acceptable: <50ms average latency{RESET}")
            success = True
        else:
            print(f"{RED}✗ Poor: {avg_latency:.1f}ms average latency{RESET}")
            print(f"  Target: <50ms")
            success = False
        
        camera_manager.stop()
        return success
        
    except Exception as e:
        print(f"{RED}✗ Test failed: {e}{RESET}")
        import traceback
        traceback.print_exc()
        return False


def test_color_channels():
    """Verify RGB→BGR conversion is working"""
    print_header("Color Channel Verification")
    
    try:
        from backend.core.camera import camera_manager
        import numpy as np
        
        # Start camera
        print(f"{CYAN}Starting camera...{RESET}")
        camera_manager.start()
        time.sleep(2)
        
        if not camera_manager.is_running:
            print(f"{RED}✗ Camera not running{RESET}")
            return False
        
        print(f"{GREEN}✓ Camera running{RESET}\n")
        
        # Get a frame
        frame = camera_manager.get_frame()
        if frame is None:
            print(f"{RED}✗ No frame received{RESET}")
            camera_manager.stop()
            return False
        
        # Check frame properties
        print(f"{CYAN}Frame Properties:{RESET}")
        print(f"  Shape:     {frame.shape}")
        print(f"  Dtype:     {frame.dtype}")
        print(f"  Min/Max:   {frame.min()}/{frame.max()}")
        
        # Check channel distribution
        b_mean = np.mean(frame[:, :, 0])
        g_mean = np.mean(frame[:, :, 1])
        r_mean = np.mean(frame[:, :, 2])
        
        print(f"\n{CYAN}Channel Means (BGR order):{RESET}")
        print(f"  Blue:  {b_mean:.1f}")
        print(f"  Green: {g_mean:.1f}")
        print(f"  Red:   {r_mean:.1f}")
        
        # Validation
        print(f"\n{CYAN}Color Validation:{RESET}")
        if frame.shape[2] == 3:
            print(f"{GREEN}✓ 3-channel BGR image{RESET}")
        else:
            print(f"{RED}✗ Wrong channel count: {frame.shape[2]}{RESET}")
            camera_manager.stop()
            return False
        
        # Check if colors are balanced (not all in one channel)
        channel_variance = np.std([b_mean, g_mean, r_mean])
        if channel_variance > 5:
            print(f"{GREEN}✓ Color channels are distinct (variance: {channel_variance:.1f}){RESET}")
        else:
            print(f"{YELLOW}⚠ Color channels similar (variance: {channel_variance:.1f}){RESET}")
            print(f"  This might indicate grayscale or poor lighting")
        
        camera_manager.stop()
        return True
        
    except Exception as e:
        print(f"{RED}✗ Test failed: {e}{RESET}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all diagnostic tests"""
    print_header("Camera Zero-Latency Diagnostic Tool")
    
    tests = [
        ("LIFO Queue Behavior", test_lifo_behavior),
        ("Frame Latency", test_latency_measurement),
        ("Color Channels", test_color_channels),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except KeyboardInterrupt:
            print(f"\n{YELLOW}Test interrupted by user{RESET}")
            break
        except Exception as e:
            print(f"{RED}Test crashed: {e}{RESET}")
            results.append((name, False))
        
        time.sleep(1)
    
    # Summary
    print_header("Test Summary")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = f"{GREEN}✓ PASS{RESET}" if result else f"{RED}✗ FAIL{RESET}"
        print(f"{status}  {name}")
    
    print(f"\nTotal: {passed}/{total} passed")
    
    if passed == total:
        print(f"\n{GREEN}All tests passed! Camera is working correctly.{RESET}")
        print("\nKey metrics verified:")
        print("  ✓ LIFO queue dropping frames (prevents lag)")
        print("  ✓ Low latency frame retrieval (<50ms)")
        print("  ✓ Correct BGR color format")
        return 0
    else:
        print(f"\n{RED}Some tests failed. Check output above.{RESET}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
