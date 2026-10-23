#!/usr/bin/env python3
"""
Integration Test for Zero-Latency Streaming

Tests that the new streaming endpoints are properly integrated into main.py
and can be accessed correctly.

Run on Raspberry Pi after deployment:
    python3 test_integration.py
"""

import sys
import time
import requests
from typing import Dict, Any

# Color codes for output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"

# Base URL - assumes server running on localhost:8000
BASE_URL = "http://localhost:8000"


def print_header(text: str) -> None:
    """Print section header"""
    print(f"\n{BLUE}{'=' * 60}{RESET}")
    print(f"{BLUE}{text:^60}{RESET}")
    print(f"{BLUE}{'=' * 60}{RESET}\n")


def print_test(name: str) -> None:
    """Print test name"""
    print(f"{YELLOW}Testing:{RESET} {name}...", end=" ", flush=True)


def print_pass() -> None:
    """Print pass result"""
    print(f"{GREEN}✓ PASS{RESET}")


def print_fail(reason: str = "") -> None:
    """Print fail result"""
    suffix = f" ({reason})" if reason else ""
    print(f"{RED}✗ FAIL{suffix}{RESET}")


def test_health_endpoint() -> bool:
    """Test that the server is running"""
    print_test("Health endpoint")
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print_pass()
            print(f"  System state: {data.get('system_state', 'unknown')}")
            print(f"  Camera FPS: {data.get('camera_fps', 0)}")
            return True
        else:
            print_fail(f"Status {response.status_code}")
            return False
    except Exception as e:
        print_fail(str(e))
        return False


def test_stream_stats() -> bool:
    """Test the streaming stats endpoint"""
    print_test("Streaming stats endpoint")
    try:
        response = requests.get(f"{BASE_URL}/api/stream/stats", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print_pass()
            producer = data.get('producer', {})
            print(f"  Frames captured: {producer.get('frames_captured', 0)}")
            print(f"  Frames dropped: {producer.get('frames_dropped', 0)}")
            print(f"  Drop rate: {producer.get('drop_rate_pct', 0):.1f}%")
            print(f"  Avg latency: {producer.get('avg_latency_ms', 0):.1f}ms")
            return True
        else:
            print_fail(f"Status {response.status_code}")
            return False
    except Exception as e:
        print_fail(str(e))
        return False


def test_mjpeg_stream() -> bool:
    """Test that MJPEG stream is accessible"""
    print_test("MJPEG stream endpoint")
    try:
        response = requests.get(
            f"{BASE_URL}/api/stream/mjpeg",
            timeout=5,
            stream=True
        )
        
        if response.status_code != 200:
            print_fail(f"Status {response.status_code}")
            return False
        
        # Read first frame to verify stream works
        content_type = response.headers.get('content-type', '')
        if 'multipart/x-mixed-replace' not in content_type:
            print_fail(f"Wrong content-type: {content_type}")
            return False
        
        # Try to read some data
        chunk = next(response.iter_content(chunk_size=1024), None)
        if not chunk:
            print_fail("No data received")
            return False
        
        print_pass()
        print(f"  Content-Type: {content_type}")
        print(f"  First chunk size: {len(chunk)} bytes")
        return True
        
    except Exception as e:
        print_fail(str(e))
        return False


def test_legacy_stream() -> bool:
    """Test that legacy /stream endpoint still works"""
    print_test("Legacy /stream endpoint")
    try:
        response = requests.get(
            f"{BASE_URL}/stream",
            timeout=5,
            stream=True
        )
        
        if response.status_code == 200:
            print_pass()
            print(f"  Status: Available (legacy endpoint)")
            return True
        else:
            print_fail(f"Status {response.status_code}")
            return False
    except Exception as e:
        print_fail(str(e))
        return False


def main():
    """Run all integration tests"""
    print_header("Zero-Latency Streaming Integration Test")
    
    print(f"Target: {BASE_URL}\n")
    
    tests = [
        ("Server Health", test_health_endpoint),
        ("Stream Stats", test_stream_stats),
        ("MJPEG Stream", test_mjpeg_stream),
        ("Legacy Stream", test_legacy_stream),
    ]
    
    results = []
    for name, test_func in tests:
        results.append(test_func())
        time.sleep(0.5)  # Brief pause between tests
    
    # Summary
    print_header("Test Summary")
    passed = sum(results)
    total = len(results)
    
    print(f"Passed: {passed}/{total}")
    print(f"Failed: {total - passed}/{total}")
    
    if passed == total:
        print(f"\n{GREEN}All tests passed! ✓{RESET}")
        print("\nNext steps:")
        print("  1. Open browser: http://localhost:8000/camera-test")
        print("  2. Test MJPEG: http://localhost:8000/api/stream/mjpeg")
        print("  3. Check stats: http://localhost:8000/api/stream/stats")
        return 0
    else:
        print(f"\n{RED}Some tests failed{RESET}")
        print("\nTroubleshooting:")
        print("  - Check if the server is running: systemctl status coffee-sorter")
        print("  - Check logs: journalctl -u coffee-sorter -f")
        print("  - Verify camera is connected: libcamera-hello --list-cameras")
        return 1


if __name__ == "__main__":
    sys.exit(main())
