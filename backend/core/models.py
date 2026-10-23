"""
Pydantic data models and shared state for Coffee Bean Sorting System.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel


# ─────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────

class Grade(str, Enum):
    GRADE_1   = "Grade 1"    # Premium quality
    GRADE_2   = "Grade 2"    # Good quality
    GRADE_3   = "Grade 3"    # Average quality
    GRADE_4   = "Grade 4"    # Defect / reject


class SystemStatus(str, Enum):
    RUNNING  = "running"
    STOPPED  = "stopped"
    PAUSED   = "paused"
    ERROR    = "error"


class AlertLevel(str, Enum):
    INFO     = "info"
    WARNING  = "warning"
    CRITICAL = "critical"


class BinType(str, Enum):
    GRADE_1 = "grade1"   # Premium  → Bin 1
    GRADE_2 = "grade2"   # Good     → Bin 2
    GRADE_3 = "grade3"   # Average  → Bin 3
    GRADE_4 = "grade4"   # Defect   → Bin 4


# ─────────────────────────────────────────────
# Bean Detection Result
# ─────────────────────────────────────────────

class BeanResult(BaseModel):
    id: int
    timestamp: str
    grade: Grade
    confidence: float          # 0–100
    size_mm: float             # measured diameter in mm
    color_r: int
    color_g: int
    color_b: int
    color_name: str            # e.g. "Uniform Brown"
    calibrated_grade: Optional[str] = None
    calibrated_hex: Optional[str] = None
    hue: float
    saturation: float
    brightness: float
    defects: list[str]         # list of detected defect tags
    roast_level: str           # "Light" / "Medium" / "Dark" / "Burnt"
    recommended_bin: BinType
    area_px: int               # contour area in pixels
    bbox_x: int
    bbox_y: int
    bbox_w: int
    bbox_h: int


# ─────────────────────────────────────────────
# Sorting Counts
# ─────────────────────────────────────────────

class SortCounts(BaseModel):
    grade1: int = 0    # Premium
    grade2: int = 0    # Good
    grade3: int = 0    # Average
    grade4: int = 0    # Defect

    @property
    def total(self) -> int:
        return self.grade1 + self.grade2 + self.grade3 + self.grade4

    def good(self) -> int:
        return self.grade1 + self.grade2 + self.grade3


# ─────────────────────────────────────────────
# System Alert
# ─────────────────────────────────────────────

class Alert(BaseModel):
    id: int
    level: AlertLevel
    title: str
    description: str
    timestamp: str
    resolved: bool = False
    source: str = "system"    # "camera" / "ejector" / "pressure" / "system"


# ─────────────────────────────────────────────
# System Stats (broadcast via WebSocket)
# ─────────────────────────────────────────────

class SystemStats(BaseModel):
    status: SystemStatus
    uptime_seconds: int
    beans_processed: int
    beans_per_minute: float
    good_yield_pct: float
    defect_rate_pct: float
    sort_counts: SortCounts
    last_bean: Optional[BeanResult]
    air_pressure_mpa: float
    conveyor_rpm: int
    camera_fps: float
    cpu_temp_c: float
    active_alerts: int


# ─────────────────────────────────────────────
# WebSocket message envelope
# ─────────────────────────────────────────────

class WSMessage(BaseModel):
    type: str          # "stats" | "bean" | "alert" | "frame" | "status"
    payload: dict


# ─────────────────────────────────────────────
# HTTP request/response bodies
# ─────────────────────────────────────────────

class SystemCommand(BaseModel):
    command: str       # "start" | "stop" | "pause" | "resume" | "reset"


class SortingSettings(BaseModel):
    conveyor_rpm: int = 180
    sensitivity: float = 0.85   # detection threshold 0–1
    min_bean_area_px: int = 400
    max_bean_area_px: int = 8000
    ejection_duration_ms: int = 40
    air_pressure_mpa: float = 0.6
    auto_sort: bool = True


# ─────────────────────────────────────────────
# Shared in-memory application state
# ─────────────────────────────────────────────

@dataclass
class AppState:
    status: SystemStatus = SystemStatus.STOPPED
    start_time: Optional[datetime] = None
    sort_counts: SortCounts = field(default_factory=SortCounts)
    recent_beans: list = field(default_factory=list)
    alerts: list = field(default_factory=list)
    settings: SortingSettings = field(default_factory=SortingSettings)
    _alert_counter: int = 0
    _bean_counter: int = 0
    _fps_actual: float = 0.0
    _pressure_mpa: float = 0.0
    calibration_ready: bool = False

    def next_bean_id(self) -> int:
        self._bean_counter += 1
        return self._bean_counter

    def next_alert_id(self) -> int:
        self._alert_counter += 1
        return self._alert_counter

    def add_bean(self, bean: BeanResult) -> None:
        self.recent_beans.insert(0, bean)
        if len(self.recent_beans) > 200:
            self.recent_beans.pop()
        count_map = {
            BinType.GRADE_1: "grade1",
            BinType.GRADE_2: "grade2",
            BinType.GRADE_3: "grade3",
            BinType.GRADE_4: "grade4",
        }
        attr = count_map[bean.recommended_bin]
        setattr(self.sort_counts, attr, getattr(self.sort_counts, attr) + 1)

    def add_alert(self, level: AlertLevel, title: str, description: str, source: str = "system") -> Alert:
        alert = Alert(
            id=self.next_alert_id(),
            level=level,
            title=title,
            description=description,
            timestamp=datetime.now().strftime("%H:%M:%S"),
            source=source,
        )
        self.alerts.insert(0, alert)
        if len(self.alerts) > 100:
            self.alerts.pop()
        return alert

    @property
    def uptime_seconds(self) -> int:
        if self.start_time is None:
            return 0
        return int((datetime.now() - self.start_time).total_seconds())

    @property
    def beans_per_minute(self) -> float:
        up = self.uptime_seconds
        if up == 0:
            return 0.0
        return round(self.sort_counts.total / (up / 60), 1)

    @property
    def good_yield_pct(self) -> float:
        t = self.sort_counts.total
        return round((self.sort_counts.good() / t) * 100, 1) if t > 0 else 0.0

    @property
    def defect_rate_pct(self) -> float:
        t = self.sort_counts.total
        return round((self.sort_counts.grade4 / t) * 100, 1) if t > 0 else 0.0

    def active_alert_count(self) -> int:
        return sum(1 for a in self.alerts if not a.resolved and a.level != AlertLevel.INFO)


# Global singleton
app_state = AppState()
