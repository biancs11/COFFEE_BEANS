"""Persistent four-grade color calibration based on pinned camera pixels."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

GRADES = ("grade1", "grade2", "grade3", "grade4")
# Distance is measured in normalized HSV coordinates: hue degrees / 3.6,
# saturation percent, and value percent. Keep this narrow so unrelated colors
# do not get assigned to whichever saved sample happens to be nearest.
MAX_CALIBRATION_DISTANCE = 12.0


def sample_hex(frame: np.ndarray, x: float, y: float, radius: int = 2) -> str:
    """Return the median RGB color around normalized frame coordinates as #RRGGBB."""
    if frame is None or frame.size == 0:
        raise ValueError("Camera frame is unavailable")
    if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
        raise ValueError("Point coordinates must be between 0 and 1")
    height, width = frame.shape[:2]
    px, py = round(x * (width - 1)), round(y * (height - 1))
    patch = frame[max(0, py-radius):min(height, py+radius+1),
                  max(0, px-radius):min(width, px+radius+1)]
    bgr = np.median(patch.reshape(-1, 3), axis=0).astype(int)
    b, g, r = (int(v) for v in bgr)
    return f"#{r:02X}{g:02X}{b:02X}"


class ColorCalibration:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.samples: dict[str, str] = {}
        self.load()

    def load(self) -> dict[str, str]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            samples = raw.get("samples", {})
            self.samples = {g: str(samples[g]).upper() for g in GRADES
                            if isinstance(samples.get(g), str)
                            and len(samples[g]) == 7 and samples[g][0] == "#"
                            and all(c in "0123456789ABCDEFabcdef" for c in samples[g][1:])}
        except (OSError, ValueError, TypeError):
            self.samples = {}
        return dict(self.samples)

    @property
    def complete(self) -> bool:
        return all(g in self.samples for g in GRADES)

    def set_sample(self, grade: str, color_hex: str) -> dict[str, str]:
        if grade not in GRADES:
            raise ValueError("Grade must be grade1, grade2, grade3, or grade4")
        if len(color_hex) != 7 or color_hex[0] != "#" or any(
            c not in "0123456789ABCDEFabcdef" for c in color_hex[1:]
        ):
            raise ValueError("Color must be a #RRGGBB hex value")
        self.samples[grade] = color_hex.upper()
        self.save()
        return dict(self.samples)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps({"samples": self.samples}, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self.path)

    def classify(self, h: float, s: float, v: float) -> str | None:
        """Return a saved grade only when measured color is near a saved hex."""
        if not self.samples:
            return None
        target = np.array([h * 2.0, s / 255.0 * 100.0, v / 255.0 * 100.0])
        distances: list[tuple[float, str]] = []
        for grade, value in self.samples.items():
            rgb = bytes.fromhex(value[1:])
            bgr = np.uint8([[[rgb[2], rgb[1], rgb[0]]]])
            sh, ss, sv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)[0, 0]
            reference = np.array([float(sh) * 2.0, float(ss) / 255 * 100,
                                  float(sv) / 255 * 100])
            # Hue wraps at red; coffee colors usually don't cross that boundary,
            # but use circular hue distance for correctness across all RGB values.
            dh = min(abs(target[0] - reference[0]), 360 - abs(target[0] - reference[0]))
            distance = (dh / 3.6) ** 2 + (target[1] - reference[1]) ** 2 + (target[2] - reference[2]) ** 2
            distances.append((float(distance), grade))
        distance, grade = min(distances)
        return grade if distance ** 0.5 <= MAX_CALIBRATION_DISTANCE else None

    def candidate_mask(self, hsv_frame: np.ndarray) -> np.ndarray | None:
        """Build broad HSV neighborhoods around calibrated colors for blob finding."""
        if not self.complete:
            return None
        height, width = hsv_frame.shape[:2]
        mask = np.zeros((height, width), dtype=np.uint8)
        for value in self.samples.values():
            rgb = bytes.fromhex(value[1:])
            bgr = np.uint8([[[rgb[2], rgb[1], rgb[0]]]])
            hue, sat, val = (int(x) for x in cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)[0, 0])
            low_s, high_s = max(0, sat - 65), min(255, sat + 65)
            low_v, high_v = max(0, val - 65), min(255, val + 65)
            low_h, high_h = hue - 10, hue + 10
            if low_h < 0:
                part = cv2.inRange(hsv_frame, np.array([0, low_s, low_v], np.uint8),
                                   np.array([high_h, high_s, high_v], np.uint8))
                part |= cv2.inRange(hsv_frame, np.array([180 + low_h, low_s, low_v], np.uint8),
                                    np.array([179, high_s, high_v], np.uint8))
            elif high_h > 179:
                part = cv2.inRange(hsv_frame, np.array([low_h, low_s, low_v], np.uint8),
                                   np.array([179, high_s, high_v], np.uint8))
                part |= cv2.inRange(hsv_frame, np.array([0, low_s, low_v], np.uint8),
                                    np.array([high_h - 180, high_s, high_v], np.uint8))
            else:
                part = cv2.inRange(hsv_frame, np.array([low_h, low_s, low_v], np.uint8),
                                   np.array([high_h, high_s, high_v], np.uint8))
            mask |= part
        return mask
