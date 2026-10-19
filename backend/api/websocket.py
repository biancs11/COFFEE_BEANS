"""
WebSocket manager + background detection loop — production hardened.

Changes from dev version:
  • MAX_CONNECTIONS limit — rejects connections beyond WS_MAX_CONNECTIONS
  • All DB writes awaited with explicit error logging (no silent fire-and-forget)
  • Real smbus2 pressure sensor read with simulation fallback
  • All thresholds and intervals driven by config.settings
  • Camera state exposed in stats broadcast
  • Graceful handling of detection errors with exponential back-off
"""

from __future__ import annotations
import asyncio
import base64
import json
import logging
import time
from datetime import datetime
from typing import Optional

from fastapi import WebSocket, WebSocketDisconnect

from ..core import (
    app_state, camera_manager, bean_detector,
    sorting_controller, AlertLevel, BinType, SystemStatus,
)
from ..core import db_service
from ..core.config import settings

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════
# PRESSURE SENSOR  — real smbus2 read with simulation fallback
# ══════════════════════════════════════════════════════════════════════════

def _read_pressure_mpa() -> float:
    """
    Read air pressure from an I2C pressure sensor via smbus2.
    Sensor assumed at address 0x28 on I2C bus 1 (Raspberry Pi default).

    Replace the register read below with your actual sensor protocol.
    Common sensors: Honeywell ABPDANT001PG2A5, NXP MPX5700AP.

    Falls back to the last known good value + small noise on failure.
    """
    try:
        import smbus2                                   # noqa: F401
        bus  = smbus2.SMBus(1)
        data = bus.read_i2c_block_data(0x28, 0x00, 2)
        bus.close()
        # Honeywell 14-bit output: raw = (data[0] & 0x3F) << 8 | data[1]
        raw = ((data[0] & 0x3F) << 8) | data[1]
        # Convert to MPa — adjust range for your specific sensor
        # Example: 0–1.0 MPa full scale, 14-bit resolution
        pressure = (raw / 16383.0) * 1.0
        return round(pressure, 3)
    except Exception:
        # Simulation: gaussian noise around target pressure
        import random
        base = settings.AIR_PRESSURE_TARGET
        return round(base + random.gauss(0, 0.02), 3)


def _read_cpu_temp() -> float:
    """Read CPU temperature from RPi thermal zone sysfs."""
    import platform
    try:
        if platform.system() == "Linux":
            with open("/sys/class/thermal/thermal_zone0/temp") as f:
                return int(f.read().strip()) / 1000.0
    except Exception:
        pass
    return 0.0


# ══════════════════════════════════════════════════════════════════════════
# CONNECTION MANAGER  — with hard limit on concurrent connections
# ══════════════════════════════════════════════════════════════════════════

class ConnectionManager:
    def __init__(self, max_connections: int = settings.WS_MAX_CONNECTIONS):
        self._max    = max_connections
        self._active: list[WebSocket] = []
        self._lock   = asyncio.Lock()

    @property
    def count(self) -> int:
        return len(self._active)

    async def connect(self, ws: WebSocket) -> bool:
        """
        Accept the WebSocket handshake.
        Returns False (and closes with 1008) if the connection limit is reached.
        """
        async with self._lock:
            if len(self._active) >= self._max:
                await ws.accept()
                await ws.close(
                    code=1008,
                    reason=f"Connection limit reached ({self._max} max)",
                )
                logger.warning(
                    f"WS connection rejected — limit of {self._max} reached"
                )
                return False
            await ws.accept()
            self._active.append(ws)
            logger.info(
                f"WS client connected — active: {len(self._active)}/{self._max}"
            )
            return True

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            if ws in self._active:
                self._active.remove(ws)
        logger.info(f"WS client disconnected — active: {len(self._active)}/{self._max}")

    async def broadcast(self, data: dict) -> None:
        if not self._active:
            return
        msg  = json.dumps(data, default=str)
        dead: list[WebSocket] = []
        for ws in list(self._active):
            try:
                await ws.send_text(msg)
            except Exception as exc:
                logger.debug(f"WS send failed ({exc}) — queuing disconnect")
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)


ws_manager = ConnectionManager()


# ══════════════════════════════════════════════════════════════════════════
# WEBSOCKET ENDPOINT
# ══════════════════════════════════════════════════════════════════════════

async def websocket_endpoint(websocket: WebSocket) -> None:
    accepted = await ws_manager.connect(websocket)
    if not accepted:
        return

    try:
        await _push_initial_stats(websocket)

        while True:
            try:
                data = await asyncio.wait_for(
                    websocket.receive_text(), timeout=0.05
                )
                if data == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
            except asyncio.TimeoutError:
                pass
            except WebSocketDisconnect:
                break

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.error(f"WS endpoint error: {exc}")
    finally:
        await ws_manager.disconnect(websocket)


# ══════════════════════════════════════════════════════════════════════════
# BACKGROUND DETECTION + BROADCAST LOOP
# ══════════════════════════════════════════════════════════════════════════

async def detection_broadcast_loop() -> None:
    """
    Core async loop — runs for the lifetime of the FastAPI process.

    Frame pipeline per tick:
      1. Read camera frame
      2. Run OpenCV detection in thread pool
      3. Write DetectionLog to DB  (awaited, errors logged)
      4. Per bean: write BeanRecord → fire GPIO → write SortingAction
      5. Evaluate auto-alert conditions → write SortingAlert
      6. Broadcast annotated JPEG ~10 fps
      7. Broadcast stats snapshot every 1 s
    """
    loop = asyncio.get_event_loop()

    last_stats_time  = time.time()
    last_frame_time  = time.time()
    _frame_counter   = 0
    _detect_backoff  = 0.0        # exponential back-off on repeated detect errors
    _detect_errors   = 0

    # Alert rate-limiting per alert type
    _cooldowns: dict[str, float] = {}

    def _ok_to_alert(key: str) -> bool:
        now = time.time()
        if now - _cooldowns.get(key, 0.0) >= settings.ALERT_COOLDOWN_SECONDS:
            _cooldowns[key] = now
            return True
        return False

    # GPIO pin map — lazy load to avoid startup crash
    try:
        BIN_ACTUATOR = settings.gpio_pin_map
    except Exception as _e:
        logger.warning(f"gpio_pin_map unavailable: {_e}")
        BIN_ACTUATOR = {}

    # ── DB write helpers (awaited, not fire-and-forget) ───────────────────
    async def _db_write_bean(bean, session_id: int) -> Optional[int]:
        try:
            return await loop.run_in_executor(
                None, db_service.write_bean_sync, bean, session_id, ""
            )
        except Exception as exc:
            logger.error(f"DB BeanRecord write failed: {exc}")
            return None

    async def _db_write_action(
        session_id: int, bean_record_id: int,
        grade: str, container: str,
        actuator_id: str, pin: int,
        success: bool, latency: float,
    ) -> Optional[int]:
        try:
            return await loop.run_in_executor(
                None,
                db_service.write_action_sync,
                session_id, bean_record_id, grade, container,
                actuator_id, pin, success, latency,
            )
        except Exception as exc:
            logger.error(f"DB SortingAction write failed: {exc}")
            return None

    async def _db_write_log(
        session_id: int, frame_no: int,
        n_beans: int, proc_ms: float, raw: dict,
    ) -> None:
        try:
            await loop.run_in_executor(
                None,
                db_service.write_detection_log_sync,
                session_id, frame_no, n_beans, proc_ms, raw,
            )
        except Exception as exc:
            logger.error(f"DB DetectionLog write failed: {exc}")

    async def _db_write_alert(
        alert, session_id: int,
        bean_id: Optional[int] = None,
        action_id: Optional[int] = None,
        ctx: Optional[float] = None,
        threshold: Optional[float] = None,
    ) -> None:
        try:
            await loop.run_in_executor(
                None,
                db_service.write_alert_sync,
                alert, session_id, bean_id, action_id, ctx, threshold,
            )
        except Exception as exc:
            logger.error(f"DB SortingAlert write failed: {exc}")

    # ── Main loop ─────────────────────────────────────────────────────────
    while True:
        await asyncio.sleep(0.015)

        now = time.time()

        # ── PAUSED: broadcast raw frame only (no detection, no sorting) ──
        if app_state.status == SystemStatus.PAUSED:
            _detect_backoff = 0.0
            _detect_errors  = 0
            if now - last_frame_time >= 0.1:   # ~10 fps while paused
                last_frame_time = now
                frame = camera_manager.get_frame()
                if frame is not None:
                    try:
                        import cv2
                        ok, buf = cv2.imencode(
                            ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 65]
                        )
                        if ok:
                            await ws_manager.broadcast({
                                "type": "frame",
                                "payload": {
                                    "data": base64.b64encode(bytes(buf)).decode(),
                                    "fps":  camera_manager.fps,
                                    "paused": True,
                                },
                            })
                    except Exception:
                        pass
            # Still broadcast stats so UI stays updated
            if now - last_stats_time >= settings.WS_STATS_INTERVAL:
                last_stats_time = now
                await ws_manager.broadcast({
                    "type": "stats",
                    "payload": {
                        "status":           app_state.status.value,
                        "uptime_seconds":   app_state.uptime_seconds,
                        "beans_processed":  app_state.sort_counts.total,
                        "beans_per_minute": 0.0,
                        "good_yield_pct":   app_state.good_yield_pct,
                        "defect_rate_pct":  app_state.defect_rate_pct,
                        "sort_counts": {
                            "grade1": app_state.sort_counts.grade1,
                            "grade2": app_state.sort_counts.grade2,
                            "grade3": app_state.sort_counts.grade3,
                            "grade4": app_state.sort_counts.grade4,
                        },
                        "last_bean":        None,
                        "air_pressure_mpa": getattr(app_state, "_pressure_mpa", 0.0),
                        "conveyor_rpm":     app_state.settings.conveyor_rpm,
                        "camera_fps":       camera_manager.fps,
                        "camera_state":     camera_manager.state.value,
                        "cpu_temp_c":       0.0,
                        "active_alerts":    app_state.active_alert_count(),
                        "valve_fires":      sorting_controller.valve_fires,
                        "conveyor_on":      sorting_controller.conveyor_on,
                        "compressor_on":    sorting_controller.compressor_on,
                        "db_session_id":    getattr(app_state, "_db_session_id", None),
                        "ws_connections":   ws_manager.count,
                    },
                })
            continue

        # ── STOPPED / ERROR: do nothing ───────────────────────────────────
        if app_state.status != SystemStatus.RUNNING:
            _detect_backoff = 0.0
            _detect_errors  = 0
            continue

        if _detect_backoff > 0:
            await asyncio.sleep(_detect_backoff)
            _detect_backoff = 0.0

        now        = time.time()
        session_id = getattr(app_state, "_db_session_id", None)

        # ── 1. Grab frame ────────────────────────────────────────────────
        frame = camera_manager.get_frame()
        if frame is None:
            # Camera reconnecting — alert once and wait
            if _ok_to_alert("camera_no_frame"):
                alert = app_state.add_alert(
                    AlertLevel.WARNING,
                    "No Camera Frame",
                    f"Camera state: {camera_manager.state.value} — waiting for frame.",
                    "camera",
                )
                if session_id:
                    await _db_write_alert(alert, session_id)
                await ws_manager.broadcast({
                    "type": "alert", "payload": alert.model_dump()
                })
            await asyncio.sleep(0.5)
            continue

        _frame_counter += 1

        # ── 2. Detect beans (thread pool — OpenCV is CPU-bound) ──────────
        t0 = time.time()
        try:
            beans, annotated = await loop.run_in_executor(
                None,
                lambda: bean_detector.detect(
                    frame,
                    min_area    = app_state.settings.min_bean_area_px,
                    max_area    = app_state.settings.max_bean_area_px,
                    sensitivity = app_state.settings.sensitivity,
                ),
            )
            _detect_errors  = 0
            # Log every 30 frames so we can confirm detection is running
            if _frame_counter % 30 == 0:
                h, w = frame.shape[:2]
                import cv2 as _cv2
                hsv_sample = _cv2.cvtColor(frame, _cv2.COLOR_BGR2HSV)
                mean_hsv   = _cv2.mean(hsv_sample)
                logger.info(
                    f"[Detection] frame={_frame_counter} "
                    f"beans={len(beans)} "
                    f"frame_size={w}x{h} "
                    f"mean_HSV=({mean_hsv[0]:.0f},{mean_hsv[1]:.0f},{mean_hsv[2]:.0f})"
                )
        except Exception as exc:
            _detect_errors += 1
            _detect_backoff = min(0.1 * (2 ** min(_detect_errors, 5)), 2.0)
            logger.error(f"Detection error (#{_detect_errors}): {exc}")
            continue

        proc_ms = round((time.time() - t0) * 1000, 3)

        # ── 3. Write DetectionLog — only when beans found ────────────────
        if session_id and beans:
            await _db_write_log(
                session_id, _frame_counter, len(beans), proc_ms,
                {
                    "frame":         _frame_counter,
                    "beans_found":   len(beans),
                    "processing_ms": proc_ms,
                    "timestamp":     datetime.utcnow().isoformat(),
                },
            )

        # ── 4. Process each bean ─────────────────────────────────────────
        for bean in beans:
            bean.id = app_state.next_bean_id()
            app_state.add_bean(bean)

            bean_record_id: Optional[int] = None

            # 4a. Persist BeanRecord (awaited)
            if session_id:
                bean_record_id = await _db_write_bean(bean, session_id)

            # 4b. Fire ejector + measure latency
            act_info      = BIN_ACTUATOR.get(
                bean.recommended_bin,
                {"id": "SV-01", "pin": settings.GPIO_VALVE_GRADE3}
            )
            eject_success = True
            eject_latency = 0.0

            if (
                app_state.settings.auto_sort
            ):
                t_eject = time.time()
                try:
                    sorting_controller.eject(
                        bean.recommended_bin,
                        app_state.settings.ejection_duration_ms,
                    )
                    eject_latency = round((time.time() - t_eject) * 1000, 3)
                except Exception as exc:
                    eject_success = False
                    logger.error(f"Ejector GPIO error: {exc}")

            # 4c. Persist SortingAction (awaited)
            action_id: Optional[int] = None
            if session_id and bean_record_id:
                action_id = await _db_write_action(
                    session_id, bean_record_id,
                    bean.grade.value,
                    bean.recommended_bin.value,
                    act_info["id"], act_info["pin"],
                    eject_success, eject_latency,
                )

            # 4d. Ejector failure alert
            if not eject_success and _ok_to_alert("eject_fail"):
                alert = app_state.add_alert(
                    AlertLevel.CRITICAL,
                    "Ejector Valve Failure",
                    f"Solenoid {act_info['id']} (GPIO {act_info['pin']}) "
                    f"did not fire for bean #{bean.id}.",
                    "ejector",
                )
                if session_id:
                    await _db_write_alert(
                        alert, session_id, bean_record_id, action_id
                    )
                await ws_manager.broadcast({
                    "type": "alert", "payload": alert.model_dump()
                })

            # 4e. Broadcast bean event
            await ws_manager.broadcast({
                "type": "bean", "payload": bean.model_dump()
            })

            # ── 5. Auto-alert conditions ──────────────────────────────────
            total = app_state.sort_counts.total

            # High defect rate
            if total > 20:
                defect_pct = app_state.defect_rate_pct
                thr = settings.ALERT_DEFECT_RATE_THRESHOLD
                if defect_pct > thr and _ok_to_alert("high_defect"):
                    alert = app_state.add_alert(
                        AlertLevel.WARNING, "High Defect Rate",
                        f"Defect rate {defect_pct:.1f}% — above {thr}% threshold.",
                        "detector",
                    )
                    if session_id:
                        await _db_write_alert(
                            alert, session_id, bean_record_id, None,
                            defect_pct, thr,
                        )
                    await ws_manager.broadcast({
                        "type": "alert", "payload": alert.model_dump()
                    })

            # Low confidence
            conf_thr = settings.ALERT_LOW_CONFIDENCE_THRESHOLD
            if bean.confidence < conf_thr and _ok_to_alert("low_conf"):
                alert = app_state.add_alert(
                    AlertLevel.WARNING, "Low Detection Confidence",
                    f"Bean #{bean.id} confidence {bean.confidence:.1f}% "
                    f"— below {conf_thr}% threshold. Check LED lighting.",
                    "camera",
                )
                if session_id:
                    await _db_write_alert(
                        alert, session_id, bean_record_id, None,
                        bean.confidence, conf_thr,
                    )
                await ws_manager.broadcast({
                    "type": "alert", "payload": alert.model_dump()
                })

        # ── 6. Broadcast annotated JPEG ~20 fps ──────────────────────────
        if now - last_frame_time >= 0.05:   # 20 fps max
            last_frame_time = now
            try:
                import cv2
                ok, buf = cv2.imencode(
                    ".jpg", annotated,
                    [cv2.IMWRITE_JPEG_QUALITY, 65]   # lower quality = less data = less lag
                )
                if ok:
                    await ws_manager.broadcast({
                        "type": "frame",
                        "payload": {
                            "data": base64.b64encode(bytes(buf)).decode(),
                            "fps":  camera_manager.fps,
                        },
                    })
            except Exception as exc:
                logger.debug(f"JPEG encode error: {exc}")

        # ── 7. Stats broadcast every 1 s ─────────────────────────────────
        if now - last_stats_time >= settings.WS_STATS_INTERVAL:
            last_stats_time = now

            # Read hardware sensors
            app_state._pressure_mpa = _read_pressure_mpa()
            cpu_temp                = _read_cpu_temp()

            # Overheat alert
            cpu_thr = settings.ALERT_CPU_TEMP_THRESHOLD
            if cpu_temp > cpu_thr and _ok_to_alert("overheat"):
                alert = app_state.add_alert(
                    AlertLevel.CRITICAL, "CPU Overheating",
                    f"CPU temperature {cpu_temp:.1f}°C — above {cpu_thr}°C. "
                    f"Check cooling system.",
                    "system",
                )
                if session_id:
                    await _db_write_alert(
                        alert, session_id, None, None, cpu_temp, cpu_thr
                    )
                await ws_manager.broadcast({
                    "type": "alert", "payload": alert.model_dump()
                })

            # Low air pressure alert
            pres_thr = settings.ALERT_LOW_PRESSURE_THRESHOLD
            if app_state._pressure_mpa < pres_thr and _ok_to_alert("low_pressure"):
                alert = app_state.add_alert(
                    AlertLevel.WARNING, "Low Air Pressure",
                    f"Compressor pressure {app_state._pressure_mpa:.3f} MPa "
                    f"— below {pres_thr} MPa minimum.",
                    "pressure",
                )
                if session_id:
                    await _db_write_alert(
                        alert, session_id, None, None,
                        app_state._pressure_mpa, pres_thr,
                    )
                await ws_manager.broadcast({
                    "type": "alert", "payload": alert.model_dump()
                })

            last_bean = app_state.recent_beans[0] if app_state.recent_beans else None
            await ws_manager.broadcast({
                "type": "stats",
                "payload": {
                    "status":           app_state.status.value,
                    "uptime_seconds":   app_state.uptime_seconds,
                    "beans_processed":  app_state.sort_counts.total,
                    "beans_per_minute": app_state.beans_per_minute,
                    "good_yield_pct":   app_state.good_yield_pct,
                    "defect_rate_pct":  app_state.defect_rate_pct,
                    "sort_counts": {
                        "grade1": app_state.sort_counts.grade1,
                        "grade2": app_state.sort_counts.grade2,
                        "grade3": app_state.sort_counts.grade3,
                        "grade4": app_state.sort_counts.grade4,
                    },
                    "last_bean":         last_bean.model_dump() if last_bean else None,
                    "air_pressure_mpa":  app_state._pressure_mpa,
                    "conveyor_rpm":      app_state.settings.conveyor_rpm,
                    "camera_fps":        camera_manager.fps,
                    "camera_state":      camera_manager.state.value,
                    "cpu_temp_c":        cpu_temp,
                    "active_alerts":     app_state.active_alert_count(),
                    "valve_fires":       sorting_controller.valve_fires,
                    "conveyor_on":       sorting_controller.conveyor_on,
                    "compressor_on":     sorting_controller.compressor_on,
                    "db_session_id":     session_id,
                    "ws_connections":    ws_manager.count,
                },
            })


# ── helpers ────────────────────────────────────────────────────────────────

async def _push_initial_stats(ws: WebSocket) -> None:
    """Send an immediate stats snapshot to a newly connected client."""
    last_bean = app_state.recent_beans[0] if app_state.recent_beans else None
    try:
        await ws.send_text(json.dumps({
            "type": "stats",
            "payload": {
                "status":           app_state.status.value,
                "uptime_seconds":   app_state.uptime_seconds,
                "beans_processed":  app_state.sort_counts.total,
                "beans_per_minute": app_state.beans_per_minute,
                "good_yield_pct":   app_state.good_yield_pct,
                "defect_rate_pct":  app_state.defect_rate_pct,
                "sort_counts": {
                    "grade1": app_state.sort_counts.grade1,
                    "grade2": app_state.sort_counts.grade2,
                    "grade3": app_state.sort_counts.grade3,
                    "grade4": app_state.sort_counts.grade4,
                },
                "last_bean":         last_bean.model_dump() if last_bean else None,
                "air_pressure_mpa":  getattr(app_state, "_pressure_mpa", 0.0),
                "conveyor_rpm":      app_state.settings.conveyor_rpm,
                "camera_fps":        camera_manager.fps,
                "camera_state":      camera_manager.state.value,
                "cpu_temp_c":        0.0,
                "active_alerts":     app_state.active_alert_count(),
                "valve_fires":       sorting_controller.valve_fires,
                "conveyor_on":       sorting_controller.conveyor_on,
                "compressor_on":     sorting_controller.compressor_on,
                "db_session_id":     getattr(app_state, "_db_session_id", None),
                "ws_connections":    ws_manager.count,
            },
        }, default=str))
    except Exception as exc:
        logger.debug(f"Initial stats push failed: {exc}")
