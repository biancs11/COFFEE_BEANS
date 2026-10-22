"""
Coffee Bean Detector v3 — Appearance-Based Multi-Stage Pipeline
================================================================

Architecture (5 stages, executed per contour):
  Stage 1 — Blob extraction    : HSV union mask + watershed separation
  Stage 2 — Bean gate          : shape geometry (circularity, solidity, aspect,
                                  size) + texture coherence via Laplacian variance
                                  → rejects pebbles, husks, dust, hands, etc.
  Stage 3 — Lighting normalise : per-frame gray-world white balance so HSV
                                  values stay stable across illumination shifts
  Stage 4 — Feature extraction : mean/std of H,S,V + 8-bin hue histogram
                                  + surface texture (Laplacian std) + shape moments
  Stage 5 — Grading            : if a trained profile is loaded, uses
                                  nearest-centroid Mahalanobis distance with
                                  per-grade covariance (learned from example images).
                                  Falls back to refined HSV-band lookup when no
                                  profile is present so the system works out-of-box.

Training workflow:
  • Drop example images (PNG/JPEG) into  data/training/<grade>/<any_name>.jpg
    where <grade> is one of: grade1  grade2  grade3  grade4
  • Call  bean_detector.train_from_examples()  (or POST /api/training/train)
  • Profiles are saved to  data/bean_profiles.json  and auto-loaded on startup.

Bean-only guarantee:
  Anything that passes the HSV mask but fails ≥ 2 of the 5 shape/texture
  checks is immediately rejected before any grading logic runs.
  This prevents hands, husk shreds, pebbles, and plastic fragments from
  ever being classified as a bean.
"""

from __future__ import annotations

import json
import logging
import math
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from .models import BeanResult, Grade, BinType

logger = logging.getLogger(__name__)

# ── Project-relative data paths (overridable via .env) ────────
_HERE = Path(__file__).resolve().parents[2]   # project root

def _resolve_training_dir() -> Path:
    try:
        from .config import settings as _s
        return _s.training_dir_path
    except Exception:
        p = _HERE / "data" / "training"
        p.mkdir(parents=True, exist_ok=True)
        return p

def _resolve_profile_path() -> Path:
    try:
        from .config import settings as _s
        return _s.profile_path
    except Exception:
        return _HERE / "data" / "bean_profiles.json"

TRAINING_DIR = _resolve_training_dir()
PROFILE_PATH = _resolve_profile_path()

def _resolve_snapshot_dir() -> Path:
    """Auto-captured frames (no beans present) waiting for human labelling."""
    try:
        from .config import settings as _s
        p = Path(_s.training_dir_path).parent / "snapshots"
    except Exception:
        p = _HERE / "data" / "snapshots"
    p.mkdir(parents=True, exist_ok=True)
    (p / "unlabelled").mkdir(exist_ok=True)
    (p / "labelled" / "grade1").mkdir(parents=True, exist_ok=True)
    (p / "labelled" / "grade2").mkdir(parents=True, exist_ok=True)
    (p / "labelled" / "grade3").mkdir(parents=True, exist_ok=True)
    (p / "labelled" / "grade4").mkdir(parents=True, exist_ok=True)
    return p

SNAPSHOT_DIR = _resolve_snapshot_dir()

# ─────────────────────────────────────────────────────────────
#  CALIBRATION
# ─────────────────────────────────────────────────────────────
PIXELS_PER_MM: float = 18.0

# ─────────────────────────────────────────────────────────────
#  FAST PRE-CHECK THRESHOLD
#  Minimum mask pixel count before running expensive watershed +
#  contour pipeline.  Below this → assume no beans present.
# ─────────────────────────────────────────────────────────────
MIN_MASK_PIXELS = 500   # raised for 1080p — at higher res beans produce more pixels

# ─────────────────────────────────────────────────────────────
#  BROAD HSV DETECTION MASK  (deliberately wide — every coffee
#  bean colour passes; the bean-gate and grader narrow it down)
# ─────────────────────────────────────────────────────────────
DETECT_LOWER = np.array([8,  25,  30], dtype=np.uint8)  # H=brown, S=min, V=min
DETECT_UPPER = np.array([38, 185, 235], dtype=np.uint8)  # H=max brown, S=max, V=max

# Green-mold band
MOLD_LOWER = np.array([28, 20, 40],  dtype=np.uint8)
MOLD_UPPER = np.array([82, 80, 150], dtype=np.uint8)

# Very dark / burnt beans (low V, near-black)
BURNT_LOWER = np.array([0,  0,  10], dtype=np.uint8)
BURNT_UPPER = np.array([180, 80, 60], dtype=np.uint8)

# ─────────────────────────────────────────────────────────────
#  SHADOW / REFLECTION / BACKGROUND REJECTION
# ─────────────────────────────────────────────────────────────
SHADOW_SAT_MAX    = 25   # near-zero S → grey background
SHADOW_VAL_MAX    = 60   # AND dark → confirmed background
REFLECTION_V_MIN  = 240  # very bright + low S → glare
REFLECTION_S_MAX  = 22

# ─────────────────────────────────────────────────────────────
#  STAGE 2 — BEAN GATE THRESHOLDS
#  Five independent checks; a blob must pass ≥ 4 of 5 to proceed
# ─────────────────────────────────────────────────────────────
MIN_AREA_PX       = 300    # noise / dust
MAX_AREA_PX       = 90000  # merged cluster (watershed handles, but extra safety)
MIN_CIRCULARITY   = 0.35   # stricter — beans are oval/round, not linear
MIN_SOLIDITY      = 0.60   # stricter — rejects irregular non-bean shapes
MAX_ASPECT_RATIO  = 3.0    # longer than 3:1 → broken shard, not a bean
MIN_DIAMETER_MM   = 4.0    # coffee beans are 6-15mm; 4mm allows calibration shots
MAX_DIAMETER_MM   = 22.0   # >22mm = merged cluster or foreign object, not a single bean
MIN_TEXTURE_LAP   = 5.0    # raised — rejects smooth plastic, glass, shiny surfaces
MAX_TEXTURE_LAP   = 900.0  # upper bound — excessive variance = paper/cloth, not a bean surface

# ─────────────────────────────────────────────────────────────
#  FALLBACK HSV GRADE BANDS  (used when no trained profile)
# ─────────────────────────────────────────────────────────────
# Grade 1 — pale cream-tan  (premium / lightly processed)
G1_H = (12, 32);  G1_S = (30, 80);  G1_V = (155, 225)
# Grade 2 — warm golden-tan  (good quality)
G2_H = (14, 32);  G2_S = (55, 130); G2_V = (140, 210)
# Grade 3 — olive / yellow-green  (average)
G3_H = (16, 45);  G3_S = (40, 155); G3_V = (75, 170)
# Grade 4 — defective (pale/mold/burnt) — catch-all remainder

# Defect sub-classifications
PALE_SAT_MAX   = 45;   PALE_VAL_MIN  = 145
MOLD_H_MIN     = 28;   MOLD_H_MAX    = 82;  MOLD_S_MIN = 18; MOLD_V_MAX = 155
BURNT_V_MAX    = 45
STD_SEVERE     = 42    # Laplacian std → "Surface Damage"
STD_MINOR      = 28    # → "Minor Surface"


# ═════════════════════════════════════════════════════════════
#  GRADE PROFILES  (loaded from JSON, built by trainer)
# ═════════════════════════════════════════════════════════════

class GradeProfiles:
    """
    Holds per-grade feature statistics learned from example images.
    Feature vector:  [mean_H, mean_S, mean_V, std_H, std_S, std_V,
                      hue_hist×8, lap_std, aspect_ratio]  → 16 dims
    """

    FEATURE_DIM = 16

    def __init__(self):
        self._profiles: dict[str, dict] = {}   # grade_key → {"mean", "std", "cov_inv", "n"}
        self._loaded = False

    def load(self, path: Path = PROFILE_PATH) -> bool:
        if not path.exists():
            return False
        try:
            data = json.loads(path.read_text())
            self._profiles = data.get("profiles", {})
            self._loaded   = bool(self._profiles)
            n = {k: v.get("n", 0) for k, v in self._profiles.items()}
            logger.info(f"GradeProfiles loaded from {path} — samples per grade: {n}")
            return self._loaded
        except Exception as exc:
            logger.error(f"Failed to load grade profiles: {exc}")
            return False

    def save(self, path: Path = PROFILE_PATH) -> bool:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({
                "version":  "3",
                "profiles": self._profiles,
                "updated":  datetime.now().isoformat(),
            }, indent=2))
            logger.info(f"GradeProfiles saved → {path}")
            return True
        except Exception as exc:
            logger.error(f"Failed to save grade profiles: {exc}")
            return False

    def update(self, grade_key: str, features: list[float]) -> None:
        """Online incremental mean/variance update (Welford's algorithm)."""
        arr = np.asarray(features, dtype=np.float64)
        if grade_key not in self._profiles:
            self._profiles[grade_key] = {
                "n":   0,
                "mean": [0.0] * self.FEATURE_DIM,
                "M2":   [0.0] * self.FEATURE_DIM,
                "std":  [1.0] * self.FEATURE_DIM,
            }
        p  = self._profiles[grade_key]
        n  = p["n"] + 1
        mu = np.asarray(p["mean"])
        M2 = np.asarray(p["M2"])
        delta  = arr - mu
        mu    += delta / n
        delta2 = arr - mu
        M2    += delta * delta2
        p["n"]    = n
        p["mean"] = mu.tolist()
        p["M2"]   = M2.tolist()
        p["std"]  = (np.sqrt(M2 / max(n - 1, 1)) + 1e-6).tolist()
        self._loaded = True

    def rebuild_from_samples(
        self,
        samples: dict[str, list[list[float]]],
    ) -> None:
        """Full rebuild from a dict of {grade_key: [feature_vec, ...]}."""
        self._profiles = {}
        for grade_key, vecs in samples.items():
            if not vecs:
                continue
            arr = np.asarray(vecs, dtype=np.float64)
            mu  = arr.mean(axis=0)
            std = arr.std(axis=0) + 1e-6
            self._profiles[grade_key] = {
                "n":    len(vecs),
                "mean": mu.tolist(),
                "std":  std.tolist(),
                "M2":   (std ** 2 * max(len(vecs) - 1, 1)).tolist(),
            }
        self._loaded = bool(self._profiles)

    @property
    def is_trained(self) -> bool:
        return self._loaded and len(self._profiles) >= 2

    def classify(
        self, features: list[float]
    ) -> tuple[str, float]:
        """
        Returns (grade_key, confidence_0_to_100).
        Uses normalised Euclidean distance to the per-grade centroid
        (each dimension divided by its std — equivalent to z-score distance).
        The grade with smallest distance wins.
        """
        if not self.is_trained:
            return "grade4", 60.0

        arr    = np.asarray(features, dtype=np.float64)
        scores: list[tuple[float, str]] = []

        for grade_key, p in self._profiles.items():
            mu  = np.asarray(p["mean"])
            std = np.asarray(p["std"])
            z   = (arr - mu) / std          # per-dimension z-scores
            dist = float(np.linalg.norm(z))  # Euclidean in z-space
            scores.append((dist, grade_key))

        scores.sort()
        best_dist, best_grade = scores[0]

        # Confidence: map distance to 0–100
        # dist=0 → 99, dist=3 → ~80, dist=6 → ~65, dist≥12 → 50
        conf = round(max(50.0, 99.0 - best_dist * 4.2), 1)

        # If the nearest grade distance is only marginally better than the
        # second nearest, reduce confidence
        if len(scores) >= 2:
            second_dist = scores[1][0]
            margin = second_dist - best_dist
            if margin < 1.0:
                conf = max(50.0, conf - (1.0 - margin) * 12)

        return best_grade, min(conf, 99.0)

    def grade_stats(self) -> dict:
        return {k: {"n": v["n"], "mean": v["mean"]} for k, v in self._profiles.items()}


# ═════════════════════════════════════════════════════════════
#  MAIN DETECTOR
# ═════════════════════════════════════════════════════════════

class BeanDetector:
    """
    Multi-stage, appearance-based coffee bean detector.

    Key public methods:
      detect(frame)           — main detection + grading (called per frame)
      train_from_examples()   — scan data/training/, build profiles, save JSON
      load_profiles()         — load previously saved profiles
      set_pixels_per_mm(ppm)  — update size calibration
    """

    def __init__(self, pixels_per_mm: float = PIXELS_PER_MM):
        self.ppm      = pixels_per_mm
        self._bean_id = 0
        self.profiles = GradeProfiles()

        # ── Snapshot / idle-state tracking ───────────────────
        # When no beans are detected for N consecutive frames we
        # auto-save a snapshot for later human labelling.
        self._no_bean_streak      = 0       # consecutive frames with no beans
        self._snapshot_interval   = 150     # save snapshot every N no-bean frames (~5s @ 30fps)
        self._snapshot_max        = 500     # max snapshots in unlabelled folder
        self._snapshot_dir        = SNAPSHOT_DIR
        self._last_snapshot_count = 0       # total snapshots saved this session

        # Try to load saved profiles immediately
        loaded = self.profiles.load()
        if loaded:
            logger.info("BeanDetector: trained profiles loaded — using ML grading")
        else:
            logger.info("BeanDetector: no profiles found — using HSV fallback grading")

    # ─────────────────────────────────────────────────────────
    def set_pixels_per_mm(self, ppm: float) -> None:
        self.ppm = max(ppm, 0.5)

    def load_profiles(self) -> bool:
        return self.profiles.load()

    # ─────────────────────────────────────────────────────────
    #  FAST PRE-CHECK  — cheap mask pixel count
    #  Runs in ~1ms (vs ~20ms for full pipeline).
    #  Returns True if enough coloured pixels exist to warrant
    #  running the full detection pipeline.
    # ─────────────────────────────────────────────────────────
    def has_beans_quick(self, frame: np.ndarray) -> bool:
        """
        Cheap pre-check: balance + HSV + inRange only.
        Returns True if mask has >= MIN_MASK_PIXELS coloured pixels.
        Use this before calling detect() to skip the expensive
        watershed + contour loop when the conveyor is empty.
        """
        if frame is None or frame.size == 0:
            return False
        try:
            norm    = self._gray_world_balance(frame)
            blurred = cv2.resize(norm, (norm.shape[1]//2, norm.shape[0]//2))  # half-res is enough
            hsv     = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)
            mask    = cv2.inRange(hsv, DETECT_LOWER, DETECT_UPPER)
            mask    = cv2.bitwise_or(mask, cv2.inRange(hsv, MOLD_LOWER,   MOLD_UPPER))
            mask    = cv2.bitwise_or(mask, cv2.inRange(hsv, BURNT_LOWER,  BURNT_UPPER))
            # Strip shadows and reflections
            s_ch = hsv[:, :, 1];  v_ch = hsv[:, :, 2]
            mask[(s_ch < SHADOW_SAT_MAX) & (v_ch < SHADOW_VAL_MAX)] = 0
            mask[(v_ch > REFLECTION_V_MIN) & (s_ch < REFLECTION_S_MAX)] = 0
            return int(cv2.countNonZero(mask)) >= MIN_MASK_PIXELS
        except Exception:
            return True   # on error, assume beans present (safe default)

    # ─────────────────────────────────────────────────────────
    #  SNAPSHOT SAVING  — captures idle frames for AI learning
    # ─────────────────────────────────────────────────────────
    def _maybe_save_snapshot(self, frame: np.ndarray) -> bool:
        """
        Called when no beans were detected this frame.
        Increments the no-bean streak counter. Every
        _snapshot_interval frames, saves the frame to
        data/snapshots/unlabelled/ for later human labelling.

        Returns True if a snapshot was saved.
        """
        self._no_bean_streak += 1

        if self._no_bean_streak % self._snapshot_interval != 0:
            return False

        try:
            unlabelled_dir = self._snapshot_dir / "unlabelled"
            # Cap total unlabelled snapshots to avoid filling the SD card
            existing = list(unlabelled_dir.glob("*.jpg"))
            if len(existing) >= self._snapshot_max:
                # Delete the oldest ones to make room (keep last 400)
                existing.sort(key=lambda p: p.stat().st_mtime)
                for old in existing[:100]:
                    old.unlink(missing_ok=True)

            import uuid as _uuid
            fname = unlabelled_dir / f"snap_{_uuid.uuid4().hex[:10]}.jpg"
            cv2.imwrite(
                str(fname), frame,
                [cv2.IMWRITE_JPEG_QUALITY, 90]
            )
            self._last_snapshot_count += 1
            logger.debug(f"Snapshot saved: {fname.name} (streak={self._no_bean_streak})")
            return True
        except Exception as exc:
            logger.warning(f"Snapshot save failed: {exc}")
            return False

    def reset_no_bean_streak(self) -> None:
        """Call when beans ARE detected to reset the idle counter."""
        self._no_bean_streak = 0

    @property
    def snapshot_stats(self) -> dict:
        """Return snapshot counts for the health/status endpoint."""
        try:
            unlabelled = len(list((self._snapshot_dir / "unlabelled").glob("*.jpg")))
            labelled   = {
                g: len(list((self._snapshot_dir / "labelled" / g).glob("*.jpg")))
                for g in ("grade1", "grade2", "grade3", "grade4")
            }
        except Exception:
            unlabelled = 0
            labelled   = {}
        return {
            "unlabelled":      unlabelled,
            "labelled":        labelled,
            "saved_session":   self._last_snapshot_count,
            "no_bean_streak":  self._no_bean_streak,
        }

    # ─────────────────────────────────────────────────────────
    #  MAIN DETECT
    # ─────────────────────────────────────────────────────────

    def detect(
        self,
        frame: np.ndarray,
        min_area: int      = MIN_AREA_PX,
        max_area: int      = MAX_AREA_PX,
        sensitivity: float = 0.85,
    ) -> tuple[list[BeanResult], np.ndarray]:

        if frame is None or frame.size == 0:
            return [], np.zeros((480, 640, 3), dtype=np.uint8)

        annotated = frame.copy()
        beans: list[BeanResult] = []

        # ── Stage 1a: Lighting normalisation (gray-world white balance) ──
        norm_frame = self._gray_world_balance(frame)

        # ── Stage 1b: Pre-process for mask building ───────────────────
        blurred  = cv2.bilateralFilter(norm_frame, d=5, sigmaColor=50, sigmaSpace=50)  # d=5 is 2x faster than d=9 at 1080p
        hsv      = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)
        # Keep original (balanced) for colour stats
        hsv_orig = cv2.cvtColor(norm_frame, cv2.COLOR_BGR2HSV)

        # ── Stage 1c: Build combined detection mask ───────────────────
        mask_main  = cv2.inRange(hsv, DETECT_LOWER, DETECT_UPPER)
        mask_mold  = cv2.inRange(hsv, MOLD_LOWER,   MOLD_UPPER)
        mask_burnt = cv2.inRange(hsv, BURNT_LOWER,   BURNT_UPPER)

        bean_mask = cv2.bitwise_or(mask_main, mask_mold)
        bean_mask = cv2.bitwise_or(bean_mask, mask_burnt)

        # ── Stage 1d: Shadow / reflection removal from mask ───────────
        s_ch = hsv[:, :, 1]
        v_ch = hsv[:, :, 2]
        shadow_px     = (s_ch < SHADOW_SAT_MAX) & (v_ch < SHADOW_VAL_MAX)
        reflection_px = (v_ch > REFLECTION_V_MIN) & (s_ch < REFLECTION_S_MAX)
        bean_mask[shadow_px | reflection_px] = 0

        # ── Stage 1e: Morphological cleanup ──────────────────────────
        k3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        k5 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        bean_mask = cv2.morphologyEx(bean_mask, cv2.MORPH_OPEN,  k3, iterations=2)
        bean_mask = cv2.morphologyEx(bean_mask, cv2.MORPH_CLOSE, k5, iterations=2)

        # ── Stage 1f: Watershed to split touching beans ───────────────
        bean_mask = self._watershed_separate(norm_frame, bean_mask)

        # ── Stage 1g: Find contours ───────────────────────────────────
        contours, _ = cv2.findContours(
            bean_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < min_area or area > max_area:
                continue

            # ── Stage 2: Bean gate ────────────────────────────────────
            bean_score, gate_info = self._bean_gate(cnt, area, norm_frame, hsv_orig)
            if bean_score < 5:  # require ALL 5 checks — strict bean-only gate
                # Failed ≥ 2 checks — not a bean
                continue

            x, y, w, h = gate_info["bbox"]
            (cx, cy), r_px = gate_info["enclosing"]
            diam_mm = (r_px * 2) / self.ppm

            # ── Stage 3: Extract per-blob colour and texture features ─
            contour_mask = np.zeros(bean_mask.shape, dtype=np.uint8)
            cv2.drawContours(contour_mask, [cnt], -1, 255, -1)
            roi_mask = contour_mask[y:y+h, x:x+w]
            roi_hsv  = hsv_orig[y:y+h, x:x+w]
            roi_bgr  = norm_frame[y:y+h, x:x+w]

            if roi_mask.sum() == 0:
                continue

            mh = cv2.mean(roi_hsv, mask=roi_mask)
            mb = cv2.mean(roi_bgr, mask=roi_mask)
            hv, sv, vv = float(mh[0]), float(mh[1]), float(mh[2])
            bv, gv, rv = int(mb[0]), int(mb[1]), int(mb[2])

            # Per-blob shadow / reflection rejection
            if sv < SHADOW_SAT_MAX and vv < SHADOW_VAL_MAX + 25:
                continue
            if vv > REFLECTION_V_MIN and sv < REFLECTION_S_MAX:
                continue

            # ── Stage 4: Full feature vector ─────────────────────────
            features = self._extract_features(
                roi_hsv, roi_bgr, roi_mask, hv, sv, vv,
                gate_info["aspect"], gate_info["solidity"]
            )

            # ── Stage 5: Grade classification ─────────────────────────
            defects      = self._detect_defects(roi_bgr, roi_mask, hv, sv, vv)
            grade, bin_t, confidence = self._classify(features, hv, sv, vv, defects)
            roast        = self._roast_label(hv, sv, vv)
            color_name   = self._color_name(hv, sv, vv)

            self._bean_id += 1
            bean = BeanResult(
                id              = self._bean_id,
                timestamp       = datetime.now().strftime("%H:%M:%S.%f")[:-3],
                grade           = grade,
                confidence      = confidence,
                size_mm         = round(diam_mm, 1),
                color_r         = rv,
                color_g         = gv,
                color_b         = bv,
                color_name      = color_name,
                hue             = round(hv, 1),
                saturation      = round(sv, 1),
                brightness      = round(vv, 1),
                defects         = defects,
                roast_level     = roast,
                recommended_bin = bin_t,
                area_px         = int(area),
                bbox_x          = int(x),
                bbox_y          = int(y),
                bbox_w          = int(w),
                bbox_h          = int(h),
            )
            beans.append(bean)
            self._annotate(annotated, bean, cx, cy, r_px)

        if beans:
            cv2.putText(
                annotated,
                f"Beans: {len(beans)}  {'[ML]' if self.profiles.is_trained else '[HSV]'}",
                (10, annotated.shape[0] - 12),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                (255, 255, 255), 2, cv2.LINE_AA,
            )
            # Reset idle counter — beans are present
            self.reset_no_bean_streak()
        else:
            # No beans detected — save snapshot for AI learning
            self._maybe_save_snapshot(frame)
            # Overlay idle indicator on annotated frame
            cv2.putText(
                annotated,
                f"No beans  {'[ML]' if self.profiles.is_trained else '[HSV]'}",
                (10, annotated.shape[0] - 12),
                cv2.FONT_HERSHEY_SIMPLEX, 0.50,
                (120, 120, 120), 1, cv2.LINE_AA,
            )

        return beans, annotated

    # ─────────────────────────────────────────────────────────
    #  LIGHTING NORMALISATION  (gray-world white balance)
    #  Divides each channel by its mean and rescales so the
    #  overall mean equals 128 — makes HSV stable under
    #  different lighting temperatures / intensities.
    # ─────────────────────────────────────────────────────────
    @staticmethod
    def _gray_world_balance(frame: np.ndarray) -> np.ndarray:
        """
        Conservative gray-world white balance.
        Only applies correction when channel imbalance is significant
        AND within a reasonable range — prevents blue/gold artifacts
        on dark conveyor backgrounds.
        """
        try:
            b, g, r = cv2.split(frame.astype(np.float32))
            bm = float(b.mean())
            gm = float(g.mean())
            rm = float(r.mean())

            # Skip correction if image is very dark (conveyor belt, no beans)
            # or if channels are already balanced enough
            avg = (bm + gm + rm) / 3.0
            if avg < 20:
                return frame  # too dark — correction would amplify noise

            # Only correct if imbalance exceeds 15% — avoid over-correcting
            max_ch = max(bm, gm, rm)
            min_ch = min(bm, gm, rm)
            if max_ch < 1 or (max_ch - min_ch) / max_ch < 0.15:
                return frame  # channels already balanced

            # Cap correction factor to avoid extreme shifts (max 1.5x per channel)
            def safe_scale(ch, cm):
                factor = min(avg / max(cm, 1), 1.5)
                return np.clip(ch * factor, 0, 255)

            b = safe_scale(b, bm)
            g = safe_scale(g, gm)
            r = safe_scale(r, rm)
            return cv2.merge([b, g, r]).astype(np.uint8)
        except Exception:
            return frame

    # ─────────────────────────────────────────────────────────
    #  STAGE 2 — BEAN GATE
    #  Returns (score 0-5, info dict).
    #  score ≥ 4 → passes (allows one failed check for partial
    #  occlusion or unusual bean shapes).
    # ─────────────────────────────────────────────────────────
    def _bean_gate(
        self,
        cnt: np.ndarray,
        area: float,
        frame: np.ndarray,
        hsv: np.ndarray,
    ) -> tuple[int, dict]:
        score = 0
        info: dict = {}

        perim = cv2.arcLength(cnt, True)
        if perim < 1:
            return 0, info

        # ① Circularity check
        circularity = (4 * math.pi * area) / (perim ** 2)
        info["circularity"] = circularity
        if circularity >= MIN_CIRCULARITY:
            score += 1

        # ② Solidity check (convex-hull fill ratio)
        hull      = cv2.convexHull(cnt)
        hull_area = cv2.contourArea(hull)
        solidity  = area / hull_area if hull_area > 0 else 0.0
        info["solidity"] = solidity
        if solidity >= MIN_SOLIDITY:
            score += 1

        # ③ Aspect ratio check
        x, y, w, h = cv2.boundingRect(cnt)
        info["bbox"] = (x, y, w, h)
        aspect = max(w, h) / max(min(w, h), 1)
        info["aspect"] = aspect
        if aspect <= MAX_ASPECT_RATIO:
            score += 1

        # ④ Size check  (diameter in mm)
        (cx, cy), r_px = cv2.minEnclosingCircle(cnt)
        info["enclosing"] = ((cx, cy), r_px)
        diam_mm = (r_px * 2) / self.ppm
        if MIN_DIAMETER_MM <= diam_mm <= MAX_DIAMETER_MM:
            score += 1

        # ⑤ Texture coherence  (Laplacian variance of ROI)
        #    Real coffee beans have a matte surface with a moderate,
        #    consistent texture.  Blank plastic/glass → too flat (low Lap).
        #    Crumpled paper / cloth → too noisy (high Lap).
        try:
            bmask = np.zeros(frame.shape[:2], dtype=np.uint8)
            cv2.drawContours(bmask, [cnt], -1, 255, -1)
            roi_gray = cv2.cvtColor(frame[y:y+h, x:x+w], cv2.COLOR_BGR2GRAY)
            rm        = bmask[y:y+h, x:x+w]
            if rm.sum() > 0:
                lap = cv2.Laplacian(roi_gray, cv2.CV_64F)
                _, lap_std = cv2.meanStdDev(lap, mask=rm)
                lap_var = float(lap_std[0][0])
                info["lap_var"] = lap_var
                if MIN_TEXTURE_LAP <= lap_var <= MAX_TEXTURE_LAP:
                    score += 1
            else:
                score += 1   # can't measure → give benefit of doubt
        except Exception:
            score += 1       # texture check failed gracefully

        return score, info

    # ─────────────────────────────────────────────────────────
    #  STAGE 4 — FEATURE EXTRACTION  (16 dimensions)
    # ─────────────────────────────────────────────────────────
    @staticmethod
    def _extract_features(
        roi_hsv: np.ndarray,
        roi_bgr: np.ndarray,
        mask: np.ndarray,
        mean_h: float,
        mean_s: float,
        mean_v: float,
        aspect: float,
        solidity: float,
    ) -> list[float]:
        # Mean and std of H, S, V
        mh, sh = mean_h, 0.0
        ms, ss = mean_s, 0.0
        mv, sv_std = mean_v, 0.0
        try:
            _, std_hsv = cv2.meanStdDev(roi_hsv, mask=mask)
            sh     = float(std_hsv[0][0])
            ss     = float(std_hsv[1][0])
            sv_std = float(std_hsv[2][0])
        except Exception:
            pass

        # 8-bin hue histogram (normalised, masked)
        hue_hist = np.zeros(8, dtype=np.float32)
        try:
            h_ch = roi_hsv[:, :, 0]
            hist = cv2.calcHist([h_ch], [0], mask, [8], [0, 180])
            total = hist.sum()
            if total > 0:
                hue_hist = (hist.flatten() / total).astype(np.float32)
        except Exception:
            pass

        # Laplacian std (surface texture roughness)
        lap_std = 0.0
        try:
            gray     = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
            lap      = cv2.Laplacian(gray, cv2.CV_64F)
            _, lst   = cv2.meanStdDev(lap, mask=mask)
            lap_std  = float(lst[0][0])
        except Exception:
            pass

        # 16 features: [mH, mS, mV, sH, sS, sV, hue_hist×8, lap_std, aspect_norm]
        # Normalise aspect: (aspect-1)/2 maps 1→0, 3→1
        aspect_norm = min(max((aspect - 1.0) / 2.0, 0.0), 1.0)

        return [
            mh, ms, mv,
            sh, ss, sv_std,
            *hue_hist.tolist(),
            lap_std,
            aspect_norm,
        ]

    # ─────────────────────────────────────────────────────────
    #  STAGE 5 — GRADE CLASSIFICATION
    # ─────────────────────────────────────────────────────────
    def _classify(
        self,
        features: list[float],
        h: float, s: float, v: float,
        defects: list[str],
    ) -> tuple[Grade, BinType, float]:

        # Always hard-route severe defects to grade 4 regardless of ML result
        severe = {"Black/Burnt", "Mold", "Pale/Damaged", "Broken"}
        if any(d in severe for d in defects):
            return Grade.GRADE_4, BinType.GRADE_4, self._defect_confidence(defects)

        # ── ML path ──────────────────────────────────────────
        if self.profiles.is_trained:
            grade_key, conf = self.profiles.classify(features)

            # Downgrade by one level when minor surface defects found
            if "Minor Surface" in defects or "Surface Damage" in defects:
                downgrade_map = {
                    "grade1": "grade2",
                    "grade2": "grade3",
                    "grade3": "grade4",
                    "grade4": "grade4",
                }
                grade_key = downgrade_map.get(grade_key, grade_key)
                conf = max(50.0, conf - 8.0)

            g, b = self._key_to_grade(grade_key)
            return g, b, round(conf, 1)

        # ── HSV fallback path ─────────────────────────────────
        return self._classify_hsv(h, s, v, defects)

    def _classify_hsv(
        self, h: float, s: float, v: float, defects: list[str]
    ) -> tuple[Grade, BinType, float]:
        minor = "Minor Surface" in defects or "Surface Damage" in defects

        # Hard gate defective zones first
        if v <= BURNT_V_MAX:
            return Grade.GRADE_4, BinType.GRADE_4, 88.0
        if (MOLD_H_MIN <= h <= MOLD_H_MAX and s >= MOLD_S_MIN and v <= MOLD_V_MAX):
            return Grade.GRADE_4, BinType.GRADE_4, 85.0
        if s < PALE_SAT_MAX and v >= PALE_VAL_MIN:
            return Grade.GRADE_4, BinType.GRADE_4, 82.0

        is_g1 = G1_H[0] <= h <= G1_H[1] and G1_S[0] <= s <= G1_S[1] and G1_V[0] <= v <= G1_V[1]
        is_g2 = G2_H[0] <= h <= G2_H[1] and G2_S[0] <= s <= G2_S[1] and G2_V[0] <= v <= G2_V[1]
        is_g3 = G3_H[0] <= h <= G3_H[1] and G3_S[0] <= s <= G3_S[1] and G3_V[0] <= v <= G3_V[1]

        # Overlap resolution: Grade 1 wins over Grade 2 when both match
        if is_g1 and not minor:
            return Grade.GRADE_1, BinType.GRADE_1, self._hsv_conf(Grade.GRADE_1, h, s, v)
        if (is_g1 or is_g2) and minor:
            return Grade.GRADE_2, BinType.GRADE_2, self._hsv_conf(Grade.GRADE_2, h, s, v) - 8
        if is_g2:
            return Grade.GRADE_2, BinType.GRADE_2, self._hsv_conf(Grade.GRADE_2, h, s, v)
        if is_g3:
            return Grade.GRADE_3, BinType.GRADE_3, self._hsv_conf(Grade.GRADE_3, h, s, v)

        return Grade.GRADE_4, BinType.GRADE_4, 72.0

    def _hsv_conf(self, grade: Grade, h: float, s: float, v: float) -> float:
        centres = {
            Grade.GRADE_1: (22.0, 55.0, 188.0),
            Grade.GRADE_2: (23.0, 88.0, 172.0),
            Grade.GRADE_3: (30.0, 95.0, 128.0),
            Grade.GRADE_4: (25.0, 30.0, 170.0),
        }
        ch, cs, cv_ = centres.get(grade, (23.0, 65.0, 165.0))
        score = 92.0
        score -= min(abs(h - ch) / 4.0  * 3.5, 10)
        score -= min(abs(s - cs) / 14.0 * 3.5,  9)
        score -= min(abs(v - cv_) / 20.0 * 3.0,  8)
        return round(max(min(score, 98.0), 55.0), 1)

    @staticmethod
    def _defect_confidence(defects: list[str]) -> float:
        base = 88.0 - len(defects) * 3
        return round(max(base, 65.0), 1)

    @staticmethod
    def _key_to_grade(key: str) -> tuple[Grade, BinType]:
        m = {
            "grade1": (Grade.GRADE_1, BinType.GRADE_1),
            "grade2": (Grade.GRADE_2, BinType.GRADE_2),
            "grade3": (Grade.GRADE_3, BinType.GRADE_3),
            "grade4": (Grade.GRADE_4, BinType.GRADE_4),
        }
        return m.get(key, (Grade.GRADE_4, BinType.GRADE_4))

    # ─────────────────────────────────────────────────────────
    #  DEFECT DETECTION
    # ─────────────────────────────────────────────────────────
    def _detect_defects(
        self,
        roi_bgr: np.ndarray,
        roi_mask: np.ndarray,
        h: float, s: float, v: float,
    ) -> list[str]:
        defects: list[str] = []

        # Black / burnt
        if v < BURNT_V_MAX:
            defects.append("Black/Burnt")
            return defects

        # Pale / washed-out (over-processed or damaged)
        if s < PALE_SAT_MAX and v >= PALE_VAL_MIN:
            defects.append("Pale/Damaged")

        # Mold (grey-green surface)
        if MOLD_H_MIN <= h <= MOLD_H_MAX and s >= MOLD_S_MIN and v <= MOLD_V_MAX:
            defects.append("Mold")

        # Surface texture damage via Laplacian std
        if roi_mask is not None and roi_bgr is not None and roi_mask.sum() > 80:
            gray     = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
            lap      = cv2.Laplacian(gray, cv2.CV_64F)
            _, lstd  = cv2.meanStdDev(lap, mask=roi_mask)
            lstd_val = float(lstd[0][0])
            if lstd_val > STD_SEVERE:
                defects.append("Surface Damage")
            elif lstd_val > STD_MINOR:
                defects.append("Minor Surface")

        # Broken (extreme aspect ratio)
        if roi_bgr is not None:
            rh, rw = roi_bgr.shape[:2]
            if rw > 0 and rh > 0:
                ratio = rw / rh
                if ratio > 2.5 or ratio < 0.35:
                    defects.append("Broken")

        return defects

    # ─────────────────────────────────────────────────────────
    #  WATERSHED SEPARATION
    # ─────────────────────────────────────────────────────────
    def _watershed_separate(
        self, frame: np.ndarray, mask: np.ndarray
    ) -> np.ndarray:
        try:
            dist       = cv2.distanceTransform(mask, cv2.DIST_L2, 5)
            _, sure_fg = cv2.threshold(dist, 0.38 * dist.max(), 255, 0)
            sure_fg    = np.uint8(sure_fg)
            k          = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
            sure_bg    = cv2.dilate(mask, k, iterations=2)
            unknown    = cv2.subtract(sure_bg, sure_fg)
            _, markers = cv2.connectedComponents(sure_fg)
            markers    = markers + 1
            markers[unknown == 255] = 0
            markers    = cv2.watershed(frame, markers)
            new_mask   = np.zeros_like(mask)
            new_mask[markers > 1] = 255
            return new_mask
        except Exception as exc:
            logger.debug(f"Watershed skipped: {exc}")
            return mask

    # ─────────────────────────────────────────────────────────
    #  DISPLAY HELPERS
    # ─────────────────────────────────────────────────────────
    def _roast_label(self, h: float, s: float, v: float) -> str:
        if v < BURNT_V_MAX:                                           return "Burnt"
        if s < PALE_SAT_MAX and v >= PALE_VAL_MIN:                   return "Pale/Damaged"
        if MOLD_H_MIN <= h <= MOLD_H_MAX and s >= MOLD_S_MIN:        return "Mold/Greenish"
        if G1_V[0] <= v and G1_S[0] <= s <= G1_S[1]:                 return "Premium (Pale Tan)"
        if G2_V[0] <= v <= G2_V[1] and G2_S[0] <= s <= G2_S[1]:     return "Good (Golden Tan)"
        if G3_V[0] <= v <= G3_V[1] and G3_S[0] <= s <= G3_S[1]:     return "Average (Olive-Green)"
        return "Unclassified"

    def _color_name(self, h: float, s: float, v: float) -> str:
        if v < BURNT_V_MAX:                                                      return "Black/Burnt"
        if s < PALE_SAT_MAX and v >= PALE_VAL_MIN:                              return "Pale/Washed-out"
        if MOLD_H_MIN <= h <= MOLD_H_MAX and s >= MOLD_S_MIN and v <= MOLD_V_MAX: return "Grey-Green (Mold)"
        if G1_H[0] <= h <= G1_H[1] and G1_S[0] <= s <= G1_S[1] and G1_V[0] <= v: return "Pale Cream-Tan"
        if G2_H[0] <= h <= G2_H[1] and G2_S[0] <= s <= G2_S[1]:               return "Warm Golden-Tan"
        if G3_H[0] <= h <= G3_H[1] and G3_S[0] <= s <= G3_S[1]:               return "Olive/Yellow-Green"
        return "Tan/Beige"

    # ─────────────────────────────────────────────────────────
    #  ANNOTATION  (draw on frame)
    # ─────────────────────────────────────────────────────────
    _COLORS = {
        Grade.GRADE_1: (0,   210, 100),   # green
        Grade.GRADE_2: (50,  160, 255),   # blue
        Grade.GRADE_3: (0,   200, 255),   # cyan
        Grade.GRADE_4: (30,   50, 235),   # red
    }
    _LABELS = {
        Grade.GRADE_1: "G1-PREMIUM",
        Grade.GRADE_2: "G2-GOOD",
        Grade.GRADE_3: "G3-AVERAGE",
        Grade.GRADE_4: "G4-DEFECT",
    }

    def _annotate(
        self,
        img: np.ndarray,
        bean: BeanResult,
        cx: float, cy: float, r_px: float,
    ) -> None:
        color  = self._COLORS.get(bean.grade, (200, 200, 200))
        label  = self._LABELS.get(bean.grade, "?")
        cx_i   = int(cx);  cy_i = int(cy);  r_i = int(r_px)

        # Circle
        cv2.circle(img, (cx_i, cy_i), r_i, color, 2)

        # Corner bracket overlay
        half = r_i + 4
        blen = max(8, r_i // 3)
        pts  = [
            ((cx_i - half, cy_i - half), (1, 0), (0, 1)),
            ((cx_i + half, cy_i - half), (-1, 0), (0, 1)),
            ((cx_i - half, cy_i + half), (1, 0), (0, -1)),
            ((cx_i + half, cy_i + half), (-1, 0), (0, -1)),
        ]
        for (px, py), (dx, dy), (ex, ey) in pts:
            cv2.line(img, (px, py), (px + dx*blen, py), color, 2)
            cv2.line(img, (px, py), (px, py + ey*blen), color, 2)

        # Grade label + confidence
        txt_conf = f"{label} {bean.confidence:.0f}%"
        ty = cy_i - r_i - 8
        if ty < 14:
            ty = cy_i + r_i + 16
        cv2.putText(
            img, txt_conf,
            (cx_i - r_i, ty),
            cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA,
        )

        # Size indicator
        cv2.putText(
            img, f"{bean.size_mm}mm",
            (cx_i - r_i, ty + 14),
            cv2.FONT_HERSHEY_SIMPLEX, 0.38, color, 1, cv2.LINE_AA,
        )

    # ─────────────────────────────────────────────────────────
    #  TRAINING  — scan example images, rebuild profiles
    # ─────────────────────────────────────────────────────────
    def train_from_examples(
        self, training_dir: Path = TRAINING_DIR
    ) -> dict:
        """
        Scan  data/training/<grade>/<image>  folders AND
              data/snapshots/labelled/<grade>/<image>  folders.

        Each image is treated as one or more bean samples:
          • Detect blobs → extract features per blob
          • If no blob found → extract from whole image ROI
            (handles tightly-cropped close-up shots)

        Rebuilds and saves bean_profiles.json.
        Returns a summary dict with per-grade sample counts.

        The more labelled images in each grade folder, the better
        the ML classifier becomes — it learns the actual colour,
        texture, and shape distribution of your specific coffee beans.
        """
        from .trainer import extract_features_from_image

        grade_keys = ["grade1", "grade2", "grade3", "grade4"]
        samples: dict[str, list[list[float]]] = {k: [] for k in grade_keys}
        stats:   dict[str, int]               = {}
        errors:  list[str]                    = []

        # ── Scan standard training dir ────────────────────────
        for grade_key in grade_keys:
            grade_dir = training_dir / grade_key
            if not grade_dir.exists():
                stats[grade_key] = 0
                continue
            img_files = [
                f for f in grade_dir.iterdir()
                if f.suffix.lower() in (".jpg", ".jpeg", ".png", ".bmp", ".webp")
            ]
            count = 0
            for img_path in img_files:
                try:
                    feats = extract_features_from_image(img_path, self.ppm)
                    if feats:
                        samples[grade_key].extend(feats)
                        count += len(feats)
                except Exception as exc:
                    errors.append(f"{img_path.name}: {exc}")
            stats[grade_key] = count

        # ── Also scan labelled snapshots ──────────────────────
        # These are auto-captured frames that a human has dragged
        # into data/snapshots/labelled/<grade>/ for AI learning.
        snap_labelled_dir = self._snapshot_dir / "labelled"
        snap_counts: dict[str, int] = {}
        if snap_labelled_dir.exists():
            for grade_key in grade_keys:
                snap_grade_dir = snap_labelled_dir / grade_key
                if not snap_grade_dir.exists():
                    snap_counts[grade_key] = 0
                    continue
                snap_files = [
                    f for f in snap_grade_dir.iterdir()
                    if f.suffix.lower() in (".jpg", ".jpeg", ".png", ".bmp", ".webp")
                ]
                count = 0
                for img_path in snap_files:
                    try:
                        feats = extract_features_from_image(img_path, self.ppm)
                        if feats:
                            samples[grade_key].extend(feats)
                            count += len(feats)
                    except Exception as exc:
                        errors.append(f"snap/{grade_key}/{img_path.name}: {exc}")
                snap_counts[grade_key] = count
                if count:
                    logger.info(f"  snapshots/{grade_key}: +{count} labelled samples")
        else:
            snap_counts = {k: 0 for k in grade_keys}

        # Merge snapshot counts into stats
        for k in grade_keys:
            stats[k] = stats.get(k, 0) + snap_counts.get(k, 0)
            logger.info(f"Training — {grade_key}: {count} samples from {len(img_files)} images")

        total = sum(stats.values())
        if total == 0:
            return {
                "ok": False,
                "message": "No training images found. Add images to data/training/<grade>/",
                "stats": stats,
                "errors": errors,
            }

        self.profiles.rebuild_from_samples(samples)
        saved = self.profiles.save()

        return {
            "ok": True,
            "message": (
                f"Trained on {total} samples across "
                f"{len([k for k,v in stats.items() if v>0])} grades."
            ),
            "stats":        stats,
            "snap_counts":  snap_counts,
            "errors":       errors,
            "saved":        saved,
            "mode":         "ML" if self.profiles.is_trained else "HSV",
        }

    def get_training_status(self) -> dict:
        return {
            "mode":          "ML" if self.profiles.is_trained else "HSV-Fallback",
            "trained":       self.profiles.is_trained,
            "grade_stats":   self.profiles.grade_stats(),
            "profile_path":  str(PROFILE_PATH),
            "training_dir":  str(TRAINING_DIR),
            "snapshot_dir":  str(SNAPSHOT_DIR),
            "snapshots":     self.snapshot_stats,
        }


# ── Module-level singleton (imported by __init__.py and routes.py) ────────
bean_detector = BeanDetector(pixels_per_mm=PIXELS_PER_MM)
