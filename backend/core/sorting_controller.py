"""
Sorting Controller — GPIO control for pneumatic air ejection system.

Hardware wiring (Raspberry Pi GPIO BCM numbering):
  GPIO 17 → Solenoid Valve 1  (Defective bin ejector)
  GPIO 27 → Solenoid Valve 2  (Premium bin gate)
  GPIO 22 → Solenoid Valve 3  (Grade 1 bin gate)
  GPIO 23 → Solenoid Valve 4  (Grade 2 bin gate)
  GPIO 24 → Solenoid Valve 5  (Grade 3 bin gate)
  GPIO 25 → Conveyor relay
  GPIO 18 → Air compressor relay

All valves are NORMALLY CLOSED — HIGH signal opens them.
"""

from __future__ import annotations
import logging
import threading
import time
from .models import BinType

logger = logging.getLogger(__name__)

# ── Try importing RPi.GPIO ────────────────────────────────────
try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
    logger.info("RPi.GPIO detected — hardware control active")
except ImportError:
    GPIO_AVAILABLE = False
    logger.warning("RPi.GPIO not found — running in simulation mode")

# ── Pin definitions ───────────────────────────────────────────
PIN_MAP: dict[BinType, int] = {
    BinType.GRADE_1: 27,   # Premium  → GPIO 27
    BinType.GRADE_2: 22,   # Good     → GPIO 22
    BinType.GRADE_3: 23,   # Average  → GPIO 23
    BinType.GRADE_4: 17,   # Defect   → GPIO 17
}
PIN_CONVEYOR    = 25
PIN_COMPRESSOR  = 18

ALL_PINS = list(PIN_MAP.values()) + [PIN_CONVEYOR, PIN_COMPRESSOR]


class SortingController:
    """
    Controls solenoid valves, conveyor relay, and compressor relay
    via Raspberry Pi GPIO.

    Thread-safe — valve pulses run in daemon threads so the main
    detection loop is not blocked.
    """

    def __init__(self, ejection_ms: int = 40):
        self.ejection_ms = ejection_ms
        self._lock = threading.Lock()
        self._active_valves: set[BinType] = set()
        self._valve_fires: dict[BinType, int] = {b: 0 for b in BinType}
        self._conveyor_on = False
        self._compressor_on = False

        if GPIO_AVAILABLE:
            self._init_gpio()

    # ── GPIO init ────────────────────────────────────────────

    def _init_gpio(self) -> None:
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        for pin in ALL_PINS:
            GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)
        logger.info("GPIO pins initialised")

    def cleanup(self) -> None:
        if GPIO_AVAILABLE:
            self.stop_conveyor()
            self.stop_compressor()
            GPIO.cleanup()
            logger.info("GPIO cleaned up")

    # ── Conveyor + Compressor ─────────────────────────────────

    def start_conveyor(self) -> None:
        self._conveyor_on = True
        if GPIO_AVAILABLE:
            GPIO.output(PIN_CONVEYOR, GPIO.HIGH)
        logger.info("Conveyor started")

    def stop_conveyor(self) -> None:
        self._conveyor_on = False
        if GPIO_AVAILABLE:
            GPIO.output(PIN_CONVEYOR, GPIO.LOW)
        logger.info("Conveyor stopped")

    def start_compressor(self) -> None:
        self._compressor_on = True
        if GPIO_AVAILABLE:
            GPIO.output(PIN_COMPRESSOR, GPIO.HIGH)
        logger.info("Air compressor started")

    def stop_compressor(self) -> None:
        self._compressor_on = False
        if GPIO_AVAILABLE:
            GPIO.output(PIN_COMPRESSOR, GPIO.LOW)
        logger.info("Air compressor stopped")

    # ── Ejection ─────────────────────────────────────────────

    def eject(self, bin_type: BinType, duration_ms: int | None = None) -> None:
        """
        Fire the solenoid valve for the given bin.
        Non-blocking — runs pulse in a daemon thread.
        Only ejects DEFECTIVE beans by default;
        other grades are routed by the layered screen mechanism.
        But the valve can be used for any bin if needed.
        """
        ms = duration_ms if duration_ms is not None else self.ejection_ms
        thread = threading.Thread(
            target=self._pulse,
            args=(bin_type, ms),
            daemon=True,
        )
        thread.start()

    def _pulse(self, bin_type: BinType, duration_ms: int) -> None:
        pin = PIN_MAP.get(bin_type)
        if pin is None:
            return
        with self._lock:
            self._active_valves.add(bin_type)
            self._valve_fires[bin_type] += 1
        try:
            if GPIO_AVAILABLE:
                GPIO.output(pin, GPIO.HIGH)
            time.sleep(duration_ms / 1000.0)
        finally:
            if GPIO_AVAILABLE:
                GPIO.output(pin, GPIO.LOW)
            with self._lock:
                self._active_valves.discard(bin_type)
            logger.debug(f"Valve {bin_type.value} fired for {duration_ms}ms")

    # ── Emergency stop ────────────────────────────────────────

    def emergency_stop(self) -> None:
        """Immediately de-energise all outputs."""
        self.stop_conveyor()
        self.stop_compressor()
        if GPIO_AVAILABLE:
            for pin in ALL_PINS:
                GPIO.output(pin, GPIO.LOW)
        with self._lock:
            self._active_valves.clear()
        logger.warning("EMERGENCY STOP — all outputs OFF")

    # ── Status ───────────────────────────────────────────────

    @property
    def active_valves(self) -> list[str]:
        with self._lock:
            return [b.value for b in self._active_valves]

    @property
    def valve_fires(self) -> dict[str, int]:
        with self._lock:
            return {b.value: c for b, c in self._valve_fires.items()}

    @property
    def total_ejections(self) -> int:
        return sum(self._valve_fires.values())

    @property
    def conveyor_on(self) -> bool:
        return self._conveyor_on

    @property
    def compressor_on(self) -> bool:
        return self._compressor_on


# Singleton
sorting_controller = SortingController()
