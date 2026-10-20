"""
Centralised configuration — reads from .env via python-dotenv.
All hardcoded values across the project are replaced by references
to this module's `settings` singleton.

Usage:
    from backend.core.config import settings
    print(settings.APP_PORT)
"""

from __future__ import annotations
from pathlib import Path
from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root is two levels up from this file
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE     = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Server ────────────────────────────────────────────────
    APP_HOST:     str = "0.0.0.0"
    APP_PORT:     int = 8000
    APP_ENV:      str = "production"
    APP_WORKERS:  int = 1
    APP_LOG_LEVEL:str = "info"

    # ── Security ──────────────────────────────────────────────
    CORS_ORIGINS: str = "http://localhost:8000,http://localhost:5173"
    API_KEY:      str = ""
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "coffeesort2024"

    # ── Database ──────────────────────────────────────────────
    DB_PATH: str = ""   # empty = use default inside data/

    # ── Logging ───────────────────────────────────────────────
    LOG_DIR:          str = "logs"
    LOG_MAX_BYTES:    int = 10_485_760   # 10 MB
    LOG_BACKUP_COUNT: int = 5

    # ── Camera ────────────────────────────────────────────────
    # Leave empty to use the default device (webcam index 0 / Pi Camera).
    # Set to an IP Webcam MJPEG URL to use a phone camera, e.g.:
    #   CAMERA_SOURCE=http://192.168.100.xxx:8080/video
    CAMERA_SOURCE:          str   = ""
    CAMERA_WIDTH:           int   = 1280
    CAMERA_HEIGHT:          int   = 720
    CAMERA_FPS:             int   = 30
    CAMERA_RECONNECT_DELAY: int   = 3
    CAMERA_MAX_FAILURES:    int   = 30

    # ── Detection ─────────────────────────────────────────────
    PIXELS_PER_MM:          float = 18.0
    MIN_BEAN_AREA:          int   = 400
    MAX_BEAN_AREA:          int   = 8000
    DETECTION_SENSITIVITY:  float = 0.85

    # ── Training / example images ─────────────────────────────
    # Directory that holds per-grade training image sub-folders.
    # Sub-folders must be named: grade1  grade2  grade3  grade4
    # Leave empty to use the default  data/training/  path.
    TRAINING_DIR:   str = ""
    # Path for the saved grade-profile JSON.
    # Leave empty to use the default  data/bean_profiles.json  path.
    PROFILE_PATH:   str = ""
    # Maximum training images stored per grade (oldest deleted when exceeded).
    # 0 = unlimited.
    MAX_TRAINING_IMAGES_PER_GRADE: int = 200

    # ── Sorting hardware ──────────────────────────────────────
    CONVEYOR_RPM:           int   = 180
    EJECTION_DURATION_MS:   int   = 40
    AIR_PRESSURE_TARGET:    float = 0.60

    # GPIO pins
    GPIO_VALVE_DEFECTIVE: int = 17
    GPIO_VALVE_PREMIUM:   int = 27
    GPIO_VALVE_GRADE1:    int = 22
    GPIO_VALVE_GRADE2:    int = 23
    GPIO_VALVE_GRADE3:    int = 24
    GPIO_CONVEYOR:        int = 25
    GPIO_COMPRESSOR:      int = 18

    # ── Alerts ────────────────────────────────────────────────
    ALERT_DEFECT_RATE_THRESHOLD:      float = 8.0
    ALERT_LOW_CONFIDENCE_THRESHOLD:   float = 70.0
    ALERT_LOW_PRESSURE_THRESHOLD:     float = 0.35
    ALERT_CPU_TEMP_THRESHOLD:         float = 80.0
    ALERT_COOLDOWN_SECONDS:           int   = 30

    # ── WebSocket ─────────────────────────────────────────────
    WS_MAX_CONNECTIONS: int   = 10
    WS_FRAME_INTERVAL:  float = 0.10
    WS_STATS_INTERVAL:  float = 1.0

    # ── Derived helpers ───────────────────────────────────────

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.lower() == "production"

    @property
    def cors_origins_list(self) -> list[str]:
        raw = [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]
        return raw

    @property
    def db_url(self) -> str:
        if self.DB_PATH:
            return f"sqlite:///{self.DB_PATH}"
        default = PROJECT_ROOT / "data" / "coffee_sorter.db"
        default.parent.mkdir(exist_ok=True)
        return f"sqlite:///{default}"

    @property
    def log_dir_path(self) -> Path:
        p = Path(self.LOG_DIR)
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def gpio_pin_map(self) -> dict:
        from backend.core.models import BinType
        return {
            BinType.GRADE_1: {"id": "SV-01", "pin": self.GPIO_VALVE_PREMIUM},
            BinType.GRADE_2: {"id": "SV-02", "pin": self.GPIO_VALVE_GRADE1},
            BinType.GRADE_3: {"id": "SV-03", "pin": self.GPIO_VALVE_GRADE2},
            BinType.GRADE_4: {"id": "SV-04", "pin": self.GPIO_VALVE_GRADE3},
        }

    @property
    def training_dir_path(self) -> Path:
        if self.TRAINING_DIR:
            p = Path(self.TRAINING_DIR)
            if not p.is_absolute():
                p = PROJECT_ROOT / p
        else:
            p = PROJECT_ROOT / "data" / "training"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def profile_path(self) -> Path:
        if self.PROFILE_PATH:
            p = Path(self.PROFILE_PATH)
            if not p.is_absolute():
                p = PROJECT_ROOT / p
            return p
        return PROJECT_ROOT / "data" / "bean_profiles.json"


# Global singleton — import this everywhere
settings = Settings()
