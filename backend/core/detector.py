"""
Coffee Bean Detector — Multi-bean, color-only, shadow-resistant detection.

Key design decisions:
  • Per-grade HSV masks combined — each grade has its own tight color range
    so beans are detected regardless of grade, not by one broad mask that
    catches shadows too.
  • Watershed segmentation — separates touching/overlapping beans into
    individual objects.
  • Shadow suppression — shadows have near-zero saturation; any blob with
    mean S < threshold AND V not in bean range is discarded.
  • Reflection suppression — very high V (>230) with low S = glare, rejected.
  • No size-based grading — grade is determined entirely by color (HSV).
  • All contours in the full frame are processed — no early exit after first bean.

Grade color bands (calibrated from real bean images):
  Grade 1 — Premium  : pale cream-tan   H14-32  S35-76  V158-215
  Grade 2 — Good     : warm golden-tan  H16-30  S52-118 V148-200
  Grade 3 — Average  : olive/yel-green  H18-42  S45-138 V80-162
  Grade 4 — Defect   : pale/mold/broken S<48&V>148 | mold | burnt
"""

from __future__ import annotations
import cv2
import numpy as np
import math
import logging
from datetime import datetime
from .models import BeanResult, Grade, BinType

logger = logging.getLogger(__name__)

# ── Calibration ───────────────────────────────────────────────
PIXELS_PER_MM: float = 18.0

# ══════════════════════════════════════════════════════════════
#  PER-GRADE HSV MASKS
#  Using separate masks for each grade prevents one broad mask
#  from pulling in shadows, background, and reflections.
#  All masks are OR-combined so every bean type is detected.
# ══════════════════════════════════════════════════════════════

# Grade 1 — pale cream-tan
G1_LOWER = np.array([14, 35,  158], dtype=np.uint8)
G1_UPPER = np.array([32, 76,  215], dtype=np.uint8)

# Grade 2 — warm golden-tan (slightly more saturated/darker than G1)
G2_LOWER = np.array([16, 52,  148], dtype=np.uint8)
G2_UPPER = np.array([30, 118, 200], dtype=np.uint8)

# Grade 3 — olive / yellow-green (greener, darker)
G3_LOWER = np.array([18, 45,  80], dtype=np.uint8)
G3_UPPER = np.array([42, 138, 162], dtype=np.uint8)

# Grade 4 — defective pale/damaged beans that still need detecting
G4_LOWER = np.array([8,  18,  80], dtype=np.uint8)
G4_UPPER = np.array([44, 47,  235], dtype=np.uint8)

# Mold (grey-green) — also Grade 4
MOLD_LOWER = np.array([28, 20, 40], dtype=np.uint8)
MOLD_UPPER = np.array([82, 80, 150], dtype=np.uint8)

# ══════════════════════════════════════════════════════════════
#  SHADOW / BACKGROUND / REFLECTION REJECTION
#
#  Dark grey mesh background: low S AND low V  → skip
#  Cast shadows:              very low S        → skip
#  Specular reflections:      very high V + low S → skip
# ══════════════════════════════════════════════════════════════
SHADOW_SAT_MAX   = 30   # S below this is a shadow or grey background
SHADOW_VAL_MAX   = 70   # AND V below this confirms background
REFLECTION_V_MIN = 235  # V above this with low S = glare
REFLECTION_S_MAX = 30

# ══════════════════════════════════════════════════════════════
#  SHAPE FILTERS
#  Beans are oval — reject shapes that are clearly not beans.
# ══════════════════════════════════════════════════════════════
MIN_CIRCULARITY  = 0.28   # oval beans — 0.28 allows elongated ones
MIN_SOLIDITY     = 0.55   # reject crescent/arc blobs (shadows)
MAX_ASPECT_RATIO = 2.8    # reject very elongated shapes
MIN_AREA_PX      = 200    # below this = noise/dust
MAX_AREA_PX      = 80000  # above this = multiple merged beans (watershed handles)
MIN_DIAMETER_MM  = 2.5    # min display size

# ══════════════════════════════════════════════════════════════
#  GRADE COLOR BANDS (used for per-blob classification)
# ══════════════════════════════════════════════════════════════
G1_HUE_MIN, G1_HUE_MAX = 14, 32
G1_SAT_MIN, G1_SAT_MAX  = 35, 76
G1_VAL_MIN, G1_VAL_MAX  = 158, 215

G2_HUE_MIN, G2_HUE_MAX = 16, 30
G2_SAT_MIN, G2_SAT_MAX  = 52, 118
G2_VAL_MIN, G2_VAL_MAX  = 148, 200

G3_HUE_MIN, G3_HUE_MAX = 18, 42
G3_SAT_MIN, G3_SAT_MAX  = 45, 138
G3_VAL_MIN, G3_VAL_MAX  = 80, 162

PALE_SAT_MAX  = 48
PALE_VAL_MIN  = 148
MOLD_H_MIN, MOLD_H_MAX = 28, 82
MOLD_S_MIN    = 20
MOLD_V_MAX    = 150
BURNT_V_MAX   = 28
STD_SEVERE    = 46
STD_MINOR     = 33


class BeanDetector:
    def __init__(self, pixels_per_mm: float = PIXELS_PER_MM):
        self.ppm      = pixels_per_mm
        self._bean_id = 0

    def set_pixels_per_mm(self, ppm: float) -> None:
        self.ppm = max(ppm, 1.0)

    # ══════════════════════════════════════════════════════════
    #  MAIN DETECT — processes ENTIRE frame, returns ALL beans
    # ══════════════════════════════════════════════════════════

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

        # ── Step 1: Pre-process — reduce noise while keeping edges ────
        # Bilateral filter: smooths colour noise but keeps bean edges sharp
        blurred = cv2.bilateralFilter(frame, d=7, sigmaColor=50, sigmaSpace=50)
        hsv     = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)
        hsv_orig = cv2.cvtColor(frame,   cv2.COLOR_BGR2HSV)

        # ── Step 2: Build combined bean mask from per-grade masks ─────
        mask_g1   = cv2.inRange(hsv, G1_LOWER,   G1_UPPER)
        mask_g2   = cv2.inRange(hsv, G2_LOWER,   G2_UPPER)
        mask_g3   = cv2.inRange(hsv, G3_LOWER,   G3_UPPER)
        mask_g4   = cv2.inRange(hsv, G4_LOWER,   G4_UPPER)
        mask_mold = cv2.inRange(hsv, MOLD_LOWER,  MOLD_UPPER)

        # Combine all grade masks
        bean_mask = cv2.bitwise_or(mask_g1,   mask_g2)
        bean_mask = cv2.bitwise_or(bean_mask, mask_g3)
        bean_mask = cv2.bitwise_or(bean_mask, mask_g4)
        bean_mask = cv2.bitwise_or(bean_mask, mask_mold)

        # ── Step 3: Shadow / reflection removal ───────────────────────
        # Shadows: S < SHADOW_SAT_MAX (near-grey)
        # Reflections: V > REFLECTION_V_MIN AND S < REFLECTION_S_MAX
        s_channel = hsv[:, :, 1]
        v_channel = hsv[:, :, 2]

        shadow_mask     = (s_channel < SHADOW_SAT_MAX) & (v_channel < SHADOW_VAL_MAX)
        reflection_mask = (v_channel > REFLECTION_V_MIN) & (s_channel < REFLECTION_S_MAX)
        noise_mask      = shadow_mask | reflection_mask

        bean_mask[noise_mask] = 0

        # ── Step 4: Morphological cleanup ─────────────────────────────
        # OPEN removes small noise blobs (dust, background specs)
        # CLOSE fills small holes inside beans
        # NO dilate — dilating merges adjacent beans
        k_small = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        k_med   = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        bean_mask = cv2.morphologyEx(bean_mask, cv2.MORPH_OPEN,  k_small, iterations=2)
        bean_mask = cv2.morphologyEx(bean_mask, cv2.MORPH_CLOSE, k_med,   iterations=2)

        # ── Step 5: Watershed to separate touching beans ──────────────
        bean_mask = self._watershed_separate(frame, bean_mask)

        # ── Step 6: Find contours and process each bean ───────────────
        contours, _ = cv2.findContours(
            bean_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < min_area or area > max_area:
                continue

            # Shape filters — reject shadows/non-bean shapes
            perim = cv2.arcLength(cnt, True)
            if perim < 1:
                continue

            circularity = (4 * math.pi * area) / (perim ** 2)
            if circularity < MIN_CIRCULARITY:
                continue

            hull      = cv2.convexHull(cnt)
            hull_area = cv2.contourArea(hull)
            if hull_area < 1:
                continue
            solidity = area / hull_area
            if solidity < MIN_SOLIDITY:
                continue

            x, y, w, h = cv2.boundingRect(cnt)
            aspect = max(w, h) / max(min(w, h), 1)
            if aspect > MAX_ASPECT_RATIO:
                continue

            # Minimum enclosing circle for size display
            (cx, cy), r_px = cv2.minEnclosingCircle(cnt)
            diam_mm = (r_px * 2) / self.ppm
            if diam_mm < MIN_DIAMETER_MM:
                continue

            # ── Step 7: Extract colour stats from ORIGINAL (unblurred) frame ──
            # Create a tight mask for this contour only
            contour_mask = np.zeros(bean_mask.shape, dtype=np.uint8)
            cv2.drawContours(contour_mask, [cnt], -1, 255, -1)

            roi_mask_full = contour_mask[y:y+h, x:x+w]
            roi_hsv       = hsv_orig[y:y+h, x:x+w]
            roi_bgr       = frame[y:y+h, x:x+w]

            if roi_mask_full.sum() == 0:
                continue

            mh = cv2.mean(roi_hsv, mask=roi_mask_full)
            mb = cv2.mean(roi_bgr, mask=roi_mask_full)
            hv, sv, vv = float(mh[0]), float(mh[1]), float(mh[2])
            bv, gv, rv = int(mb[0]), int(mb[1]), int(mb[2])

            # ── Step 8: Per-blob shadow / reflection rejection ────────
            # A genuine bean has enough saturation to not be a shadow
            if sv < SHADOW_SAT_MAX and vv < SHADOW_VAL_MAX + 20:
                continue   # shadow or dark background
            if vv > REFLECTION_V_MIN and sv < REFLECTION_S_MAX:
                continue   # specular reflection

            # ── Step 9: Classify by colour ────────────────────────────
            defects      = self._detect_defects(roi_bgr, roi_mask_full, hv, sv, vv)
            grade, bin_t = self._classify_by_color(hv, sv, vv, defects)
            roast        = self._roast_label(hv, sv, vv)
            color_name   = self._color_name(hv, sv, vv)
            confidence   = self._confidence(grade, hv, sv, vv, defects)

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

        # Draw bean count on frame
        if beans:
            cv2.putText(
                annotated,
                f"Beans: {len(beans)}",
                (10, annotated.shape[0] - 12),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                (255, 255, 255), 2, cv2.LINE_AA,
            )

        return beans, annotated

    # ══════════════════════════════════════════════════════════
    #  WATERSHED SEPARATION
    #  Splits touching/overlapping beans into individual objects.
    #  Works by finding sure-foreground (distance transform peaks)
    #  and sure-background, then letting watershed fill the markers.
    # ══════════════════════════════════════════════════════════

    def _watershed_separate(self, frame: np.ndarray, mask: np.ndarray) -> np.ndarray:
        try:
            # Distance transform — peak inside each bean
            dist   = cv2.distanceTransform(mask, cv2.DIST_L2, 5)

            # Sure foreground: pixels far from any edge (inside bean bodies)
            # Threshold at 40% of max distance — lower = more splits
            _, sure_fg = cv2.threshold(dist, 0.40 * dist.max(), 255, 0)
            sure_fg    = np.uint8(sure_fg)

            # Sure background: dilated mask
            kernel  = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
            sure_bg = cv2.dilate(mask, kernel, iterations=2)

            # Unknown region
            unknown = cv2.subtract(sure_bg, sure_fg)

            # Label markers
            _, markers = cv2.connectedComponents(sure_fg)
            markers    = markers + 1          # background = 1, not 0
            markers[unknown == 255] = 0       # unknown = 0

            # Run watershed
            markers = cv2.watershed(frame, markers)

            # Rebuild mask: keep all markers > 1 (each bean gets its own label)
            new_mask = np.zeros_like(mask)
            new_mask[markers > 1] = 255
            return new_mask

        except Exception as exc:
            logger.debug(f"Watershed failed: {exc} — using original mask")
            return mask

    # ══════════════════════════════════════════════════════════
    #  DEFECT DETECTION
    # ══════════════════════════════════════════════════════════

    def _detect_defects(self, roi_bgr, roi_mask, h, s, v) -> list[str]:
        defects = []

        if v < BURNT_V_MAX:
            defects.append("Black/Burnt")
            return defects

        # Pale / washed-out
        if s < PALE_SAT_MAX and v >= PALE_VAL_MIN:
            defects.append("Pale/Damaged")

        # Mold
        if MOLD_H_MIN <= h <= MOLD_H_MAX and s >= MOLD_S_MIN and v <= MOLD_V_MAX:
            defects.append("Mold")

        # Surface damage (high brightness variance)
        if roi_mask is not None and roi_bgr is not None and roi_mask.sum() > 80:
            gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
            _, std = cv2.meanStdDev(gray, mask=roi_mask)
            std_v = float(std[0][0])
            if std_v > STD_SEVERE:
                defects.append("Surface Damage")
            elif std_v > STD_MINOR:
                defects.append("Minor Surface")

        # Broken shape
        if roi_bgr is not None:
            bh_r, bw_r = roi_bgr.shape[:2]
            if bw_r > 0 and bh_r > 0:
                ratio = bw_r / bh_r
                if ratio > 2.3 or ratio < 0.38:
                    defects.append("Broken")

        return defects

    # ══════════════════════════════════════════════════════════
    #  COLOR-ONLY GRADING
    # ══════════════════════════════════════════════════════════

    def _classify_by_color(self, h, s, v, defects) -> tuple[Grade, BinType]:

        severe = {"Black/Burnt", "Mold", "Pale/Damaged", "Broken", "Surface Damage"}
        if any(d in severe for d in defects):
            return Grade.GRADE_4, BinType.GRADE_4

        minor = "Minor Surface" in defects

        is_g1 = (
            G1_HUE_MIN <= h <= G1_HUE_MAX and
            G1_SAT_MIN <= s < 76 and
            G1_VAL_MIN <= v <= G1_VAL_MAX
        )
        is_g2 = (
            G2_HUE_MIN <= h <= G2_HUE_MAX and
            G2_SAT_MIN <= s <= G2_SAT_MAX and
            G2_VAL_MIN <= v <= G2_VAL_MAX and
            not is_g1
        )
        is_g3 = (
            G3_HUE_MIN <= h <= G3_HUE_MAX and
            G3_SAT_MIN <= s <= G3_SAT_MAX and
            G3_VAL_MIN <= v <= G3_VAL_MAX and
            not is_g1 and not is_g2
        )

        if is_g1:
            return (Grade.GRADE_2, BinType.GRADE_2) if minor else (Grade.GRADE_1, BinType.GRADE_1)
        if is_g2:
            return (Grade.GRADE_3, BinType.GRADE_3) if minor else (Grade.GRADE_2, BinType.GRADE_2)
        if is_g3:
            return Grade.GRADE_3, BinType.GRADE_3

        return Grade.GRADE_4, BinType.GRADE_4

    # ══════════════════════════════════════════════════════════
    #  CONFIDENCE
    # ══════════════════════════════════════════════════════════

    def _confidence(self, grade, h, s, v, defects) -> float:
        centres = {
            Grade.GRADE_1: (23.0, 58.0, 185.0),
            Grade.GRADE_2: (23.0, 82.0, 170.0),
            Grade.GRADE_3: (28.0, 88.0, 125.0),
            Grade.GRADE_4: (25.0, 35.0, 175.0),
        }
        ih, is_, iv = centres.get(grade, (23.0, 65.0, 165.0))
        score = 94.0
        score -= min(abs(h - ih) / 5.0  * 4, 10)
        score -= min(abs(s - is_) / 15.0 * 4,  8)
        score -= min(abs(v - iv) / 20.0  * 3,  6)
        score -= len(defects) * 5
        return round(max(min(score, 99.0), 50.0), 1)

    # ══════════════════════════════════════════════════════════
    #  DISPLAY HELPERS
    # ══════════════════════════════════════════════════════════

    def _roast_label(self, v, s, h) -> str:
        if v < BURNT_V_MAX:                                      return "Burnt"
        if s < PALE_SAT_MAX and v >= PALE_VAL_MIN:               return "Pale/Damaged"
        if MOLD_H_MIN <= h <= MOLD_H_MAX and s >= MOLD_S_MIN:    return "Mold/Greenish"
        if G1_VAL_MIN <= v and G1_SAT_MIN <= s < 76:             return "Premium (Pale Tan)"
        if G2_VAL_MIN <= v <= G2_VAL_MAX and G2_SAT_MIN <= s:    return "Good (Golden Tan)"
        if G3_VAL_MIN <= v <= G3_VAL_MAX and G3_SAT_MIN <= s:    return "Average (Olive-Green)"
        return "Unclassified"

    def _color_name(self, h, s, v) -> str:
        if v < BURNT_V_MAX:                                                      return "Black/Burnt"
        if s < PALE_SAT_MAX and v >= PALE_VAL_MIN:                              return "Pale/Washed-out"
        if MOLD_H_MIN <= h <= MOLD_H_MAX and s >= MOLD_S_MIN and v <= MOLD_V_MAX: return "Grey-Green (Mold)"
        if G1_HUE_MIN <= h <= G1_HUE_MAX and G1_SAT_MIN <= s < 76 and G1_VAL_MIN <= v: return "Pale Cream-Tan"
        if G2_HUE_MIN <= h <= G2_HUE_MAX and G2_SAT_MIN <= s <= G2_SAT_MAX:    return "Warm Golden-Tan"
        if G3_HUE_MIN <= h <= G3_HUE_MAX and G3_SAT_MIN <= s <= G3_SAT_MAX:    return "Olive/Yellow-Green"
        return "Tan/Beige"

    # ══════════════════════════════════════════════════════════
    #  ANNOTATION
    # ══════════════════════════════════════════════════════════

    COLORS = {
        Grade.GRADE_1: (0,   210, 100),   # green
        Grade.GRADE_2: (50,  160, 255),   # blue
        Grade.GRADE_3: (0,   210, 255),   # cyan
        Grade.GRADE_4: (30,   50, 235),   # red
    }
    LABELS = {
        Grade.GRADE_1: "GRADE 1 - PREMIUM",
        Grade.GRADE_2: "GRADE 2 - GOOD",
        Grade.GRADE_3: "GRADE 3 - AVERAGE",
        Grade.GRADE_4: "GRADE 4 - DEFECT",
    }

    def _annotate(self, frame, bean, cx, cy, r_px):
        color = self.COLORS.get(bean.grade, (200, 200, 200))
        label = self.LABELS.get(bean.grade, str(bean.grade))
        cxi, cyi, ri = int(cx), int(cy), int(r_px)
        bx, by, bw, bh = bean.bbox_x, bean.bbox_y, bean.bbox_w, bean.bbox_h

        # Circle around bean
        cv2.circle(frame, (cxi, cyi), ri + 3, color, 2)

        # Corner brackets
        cl = max(8, min(bw, bh) // 4)
        for (px, py), (dx, dy) in [
            ((bx,    by),    ( 1,  1)),
            ((bx+bw, by),    (-1,  1)),
            ((bx,    by+bh), ( 1, -1)),
            ((bx+bw, by+bh), (-1, -1)),
        ]:
            cv2.line(frame, (px, py), (px + dx*cl, py),         color, 2)
            cv2.line(frame, (px, py), (px,          py + dy*cl), color, 2)

        # Grade label
        font = cv2.FONT_HERSHEY_SIMPLEX
        txt  = f"{label}  {bean.confidence:.0f}%"
        (tw, th), _ = cv2.getTextSize(txt, font, 0.40, 1)
        lx = max(bx, 0)
        ly = max(by - 5, th + 5)
        cv2.rectangle(frame, (lx, ly-th-4), (lx+tw+6, ly+2), color, -1)
        cv2.putText(frame, txt, (lx+3, ly-1), font, 0.40, (0, 0, 0), 1, cv2.LINE_AA)

        # Size mm
        cv2.putText(frame, f"{bean.size_mm}mm",
                    (cxi - 14, cyi + 4), font, 0.38, color, 1, cv2.LINE_AA)


bean_detector = BeanDetector()
