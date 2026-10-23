"""
Coffee Bean Trainer
===================
Handles everything related to building grade profiles from example images.

Public interface:
  extract_features_from_image(path, ppm)  — extract feature vectors from one image
  scan_training_dir(training_dir, ppm)    — scan all grade folders, return sample dict
  build_profiles_from_dir(training_dir, ppm) → dict summary
  save_roi_crop(image_bytes, grade_key, training_dir) → saved path

Folder layout expected (created automatically if absent):
  data/training/
      grade1/   ← Grade 1 – Premium example images
      grade2/   ← Grade 2 – Good
      grade3/   ← Grade 3 – Average
      grade4/   ← Grade 4 – Defect / rejected

Image types accepted:  .jpg  .jpeg  .png  .bmp  .webp

Each image may contain:
  • A single bean (close-up photo / lab capture)
  • Multiple beans of the same grade (batch sample photo)
For multi-bean images every detected blob is treated as an independent sample.
If zero beans are detected the whole image ROI is used as a single sample
(handles strongly cropped close-ups where the bean fills the frame).
"""

from __future__ import annotations

import logging
import shutil
import uuid
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)

GRADE_KEYS = ["grade1", "grade2", "grade3", "grade4"]

# ─────────────────────────────────────────────────────────────
#  DETECTION CONSTANTS (mirrors detector.py values — kept local
#  so this module stays importable without the full detector)
# ─────────────────────────────────────────────────────────────
_DETECT_LOWER = np.array([5,  15,  40], dtype=np.uint8)
_DETECT_UPPER = np.array([45, 200, 240], dtype=np.uint8)
_MOLD_LOWER   = np.array([28, 20,  40], dtype=np.uint8)
_MOLD_UPPER   = np.array([82, 80, 150], dtype=np.uint8)
_BURNT_LOWER  = np.array([0,  0,   10], dtype=np.uint8)
_BURNT_UPPER  = np.array([180, 80, 60], dtype=np.uint8)

_SHADOW_SAT_MAX  = 25
_SHADOW_VAL_MAX  = 60
_REFL_V_MIN      = 240
_REFL_S_MAX      = 22

_MIN_AREA   = 250
_MAX_AREA   = 90_000
_MIN_CIRC   = 0.22   # slightly relaxed for close-up training images
_MIN_SOLID  = 0.48
_MAX_ASPECT = 3.2
_FEATURE_DIM = 16


# ═════════════════════════════════════════════════════════════
#  FEATURE EXTRACTION  (shared with detector — same 16 dims)
# ═════════════════════════════════════════════════════════════

def _feature_from_roi(
    roi_hsv: np.ndarray,
    roi_bgr: np.ndarray,
    mask: Optional[np.ndarray],
) -> list[float]:
    """Build a 16-dim feature vector from a single bean ROI."""
    if mask is None:
        mask = np.ones(roi_bgr.shape[:2], dtype=np.uint8) * 255

    # Mean HSV
    mh = cv2.mean(roi_hsv, mask=mask)
    mean_h, mean_s, mean_v = float(mh[0]), float(mh[1]), float(mh[2])

    # Std HSV
    _, std_hsv = cv2.meanStdDev(roi_hsv, mask=mask)
    std_h = float(std_hsv[0][0])
    std_s = float(std_hsv[1][0])
    std_v = float(std_hsv[2][0])

    # 8-bin normalised hue histogram
    h_ch     = roi_hsv[:, :, 0]
    hue_hist = np.zeros(8, dtype=np.float32)
    try:
        hist  = cv2.calcHist([h_ch], [0], mask, [8], [0, 180])
        total = hist.sum()
        if total > 0:
            hue_hist = (hist.flatten() / total).astype(np.float32)
    except Exception:
        pass

    # Laplacian std (surface texture)
    lap_std = 0.0
    try:
        gray    = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
        lap     = cv2.Laplacian(gray, cv2.CV_64F)
        _, lstd = cv2.meanStdDev(lap, mask=mask)
        lap_std = float(lstd[0][0])
    except Exception:
        pass

    # Aspect ratio (0..1 normalised)
    rh, rw   = roi_bgr.shape[:2]
    aspect   = max(rw, rh) / max(min(rw, rh), 1)
    asp_norm = min(max((aspect - 1.0) / 2.0, 0.0), 1.0)

    return [
        mean_h, mean_s, mean_v,
        std_h,  std_s,  std_v,
        *hue_hist.tolist(),
        lap_std,
        asp_norm,
    ]


def _detect_blobs(frame: np.ndarray) -> list[tuple[np.ndarray, tuple, np.ndarray]]:
    """
    Detect bean-like blobs in a training image.
    Returns list of (contour, (x,y,w,h), roi_mask).
    """
    norm    = frame
    blurred = cv2.bilateralFilter(norm, d=9, sigmaColor=60, sigmaSpace=60)
    hsv     = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)

    mask  = cv2.bitwise_or(cv2.inRange(hsv, _DETECT_LOWER, _DETECT_UPPER),
                           cv2.inRange(hsv, _MOLD_LOWER,   _MOLD_UPPER))
    mask  = cv2.bitwise_or(mask, cv2.inRange(hsv, _BURNT_LOWER, _BURNT_UPPER))

    s_ch  = hsv[:, :, 1];  v_ch = hsv[:, :, 2]
    mask[(s_ch < _SHADOW_SAT_MAX) & (v_ch < _SHADOW_VAL_MAX)] = 0
    mask[(v_ch > _REFL_V_MIN)     & (s_ch < _REFL_S_MAX)]     = 0

    k3   = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    k5   = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,  k3, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k5, iterations=2)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    blobs: list[tuple[np.ndarray, tuple, np.ndarray]] = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < _MIN_AREA or area > _MAX_AREA:
            continue

        perim = cv2.arcLength(cnt, True)
        if perim < 1:
            continue

        circ    = (4 * 3.14159 * area) / (perim ** 2)
        hull_a  = cv2.contourArea(cv2.convexHull(cnt)) or 1
        solid   = area / hull_a
        x, y, w, h = cv2.boundingRect(cnt)
        aspect  = max(w, h) / max(min(w, h), 1)

        passes = sum([
            circ   >= _MIN_CIRC,
            solid  >= _MIN_SOLID,
            aspect <= _MAX_ASPECT,
        ])
        if passes < 2:
            continue

        roi_mask = np.zeros(mask.shape, dtype=np.uint8)
        cv2.drawContours(roi_mask, [cnt], -1, 255, -1)
        blobs.append((cnt, (x, y, w, h), roi_mask[y:y+h, x:x+w]))

    return blobs


# ═════════════════════════════════════════════════════════════
#  PUBLIC API
# ═════════════════════════════════════════════════════════════

def extract_features_from_image(
    path: Path,
    ppm: float = 18.0,
) -> list[list[float]]:
    """
    Load one training image and return a list of 16-dim feature vectors,
    one per detected bean.  Falls back to whole-image ROI if no beans found.
    """
    img = cv2.imread(str(path))
    if img is None:
        # Try via numpy (handles some exotic paths / filenames)
        try:
            import numpy as np
            buf = np.frombuffer(Path(path).read_bytes(), dtype=np.uint8)
            img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
        except Exception:
            pass
    if img is None:
        raise ValueError(f"Cannot read image: {path}")

    # Resize very large images to keep feature extraction fast
    h, w = img.shape[:2]
    if max(h, w) > 1600:
        scale = 1600 / max(h, w)
        img   = cv2.resize(img, (int(w * scale), int(h * scale)))

    norm   = img
    hsv    = cv2.cvtColor(norm, cv2.COLOR_BGR2HSV)
    blobs  = _detect_blobs(img)

    features: list[list[float]] = []

    if blobs:
        for cnt, (x, y, bw, bh), roi_mask in blobs:
            roi_hsv = hsv[y:y+bh, x:x+bw]
            roi_bgr = norm[y:y+bh, x:x+bw]
            if roi_mask.shape[:2] == roi_bgr.shape[:2] and roi_mask.sum() > 0:
                feat = _feature_from_roi(roi_hsv, roi_bgr, roi_mask)
                features.append(feat)
    else:
        # No blobs detected — treat whole image as one bean sample
        # (common for tightly-cropped close-up shots)
        feat = _feature_from_roi(hsv, norm, None)
        features.append(feat)
        logger.debug(f"No blobs in {path.name} — using whole-image ROI")

    return features


def scan_training_dir(
    training_dir: Path,
    ppm: float = 18.0,
) -> tuple[dict[str, list[list[float]]], dict[str, int], list[str]]:
    """
    Scan all grade sub-folders and collect feature vectors.

    Returns:
        samples  — {grade_key: [[feat_vec], ...]}
        stats    — {grade_key: sample_count}
        errors   — [error_string, ...]
    """
    samples: dict[str, list[list[float]]] = {k: [] for k in GRADE_KEYS}
    stats:   dict[str, int]               = {k: 0  for k in GRADE_KEYS}
    errors:  list[str]                    = []

    for grade_key in GRADE_KEYS:
        grade_dir = training_dir / grade_key
        if not grade_dir.exists():
            logger.debug(f"Training dir not found: {grade_dir}")
            continue

        img_files = sorted([
            f for f in grade_dir.iterdir()
            if f.suffix.lower() in (".jpg", ".jpeg", ".png", ".bmp", ".webp")
        ])

        for img_path in img_files:
            try:
                feats = extract_features_from_image(img_path, ppm)
                if feats:
                    samples[grade_key].extend(feats)
            except Exception as exc:
                msg = f"{grade_key}/{img_path.name}: {exc}"
                errors.append(msg)
                logger.warning(f"Training image error — {msg}")

        stats[grade_key] = len(samples[grade_key])
        if stats[grade_key]:
            logger.info(f"  {grade_key}: {stats[grade_key]} samples from {len(img_files)} images")

    return samples, stats, errors


def save_uploaded_image(
    image_bytes: bytes,
    grade_key: str,
    training_dir: Path,
    original_filename: str = "",
) -> Path:
    """
    Save a user-uploaded image to the correct grade folder.
    Returns the saved file path.
    """
    if grade_key not in GRADE_KEYS:
        raise ValueError(f"Invalid grade key '{grade_key}'. Must be one of {GRADE_KEYS}")

    dest_dir = training_dir / grade_key
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Determine extension from original filename, default to .jpg
    ext = ".jpg"
    if original_filename:
        sfx = Path(original_filename).suffix.lower()
        if sfx in (".jpg", ".jpeg", ".png", ".bmp", ".webp"):
            ext = sfx

    # Unique filename to avoid collisions
    filename = f"{uuid.uuid4().hex[:12]}{ext}"
    dest     = dest_dir / filename

    dest.write_bytes(image_bytes)
    logger.info(f"Saved training image: {dest}")
    return dest


def delete_training_image(path: Path) -> bool:
    """Delete a single training image file."""
    try:
        path.unlink(missing_ok=True)
        return True
    except Exception as exc:
        logger.error(f"Failed to delete training image {path}: {exc}")
        return False


def clear_grade_folder(training_dir: Path, grade_key: str) -> int:
    """
    Delete all images in one grade folder.
    Returns count of deleted files.
    """
    grade_dir = training_dir / grade_key
    if not grade_dir.exists():
        return 0
    count = 0
    for f in grade_dir.iterdir():
        if f.suffix.lower() in (".jpg", ".jpeg", ".png", ".bmp", ".webp"):
            try:
                f.unlink()
                count += 1
            except Exception:
                pass
    return count


def list_training_images(training_dir: Path) -> dict[str, list[dict]]:
    """
    Return a dict of grade_key → list of image metadata dicts.
    Each dict has: {filename, size_bytes, path}
    """
    result: dict[str, list[dict]] = {}
    for grade_key in GRADE_KEYS:
        grade_dir = training_dir / grade_key
        imgs: list[dict] = []
        if grade_dir.exists():
            for f in sorted(grade_dir.iterdir()):
                if f.suffix.lower() in (".jpg", ".jpeg", ".png", ".bmp", ".webp"):
                    try:
                        imgs.append({
                            "filename":   f.name,
                            "size_bytes": f.stat().st_size,
                            "path":       str(f),
                        })
                    except Exception:
                        pass
        result[grade_key] = imgs
    return result


# ═════════════════════════════════════════════════════════════
#  SNAPSHOT MANAGEMENT
#  Auto-captured idle frames stored in data/snapshots/
#  Unlabelled = waiting for human review
#  Labelled   = moved to grade sub-folder, used in training
# ═════════════════════════════════════════════════════════════

def save_snapshot(
    frame_bgr: "np.ndarray",
    snapshot_dir: Path,
    quality: int = 90,
) -> Path:
    """
    Save a raw camera frame to data/snapshots/unlabelled/.
    Called by the detector when no beans are present.

    Args:
        frame_bgr:    OpenCV BGR numpy array
        snapshot_dir: base snapshot dir (data/snapshots/)
        quality:      JPEG quality (default 90)

    Returns the saved file path.
    """
    import uuid as _uuid
    unlabelled = snapshot_dir / "unlabelled"
    unlabelled.mkdir(parents=True, exist_ok=True)

    fname = unlabelled / f"snap_{_uuid.uuid4().hex[:10]}.jpg"
    cv2.imwrite(str(fname), frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, quality])
    logger.debug(f"Snapshot saved: {fname}")
    return fname


def label_snapshot(
    snapshot_dir: Path,
    filename: str,
    grade_key: str,
) -> Path:
    """
    Move a snapshot from unlabelled/ to labelled/<grade_key>/.
    This makes it available for the next training run.

    Args:
        snapshot_dir: base snapshot dir (data/snapshots/)
        filename:     just the filename, e.g. "snap_abc123.jpg"
        grade_key:    one of grade1 / grade2 / grade3 / grade4

    Returns the new destination path.
    Raises ValueError on invalid grade or missing file.
    """
    if grade_key not in GRADE_KEYS:
        raise ValueError(f"Invalid grade '{grade_key}'. Must be one of {GRADE_KEYS}")

    src = snapshot_dir / "unlabelled" / Path(filename).name
    if not src.exists():
        raise FileNotFoundError(f"Snapshot not found: {filename}")

    dest_dir = snapshot_dir / "labelled" / grade_key
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name

    shutil.move(str(src), str(dest))
    logger.info(f"Snapshot labelled: {src.name} → {grade_key}/")
    return dest


def delete_snapshot(snapshot_dir: Path, filename: str) -> bool:
    """
    Delete a snapshot from unlabelled/ (reject it — not useful for training).
    Returns True on success.
    """
    target = snapshot_dir / "unlabelled" / Path(filename).name
    try:
        target.unlink(missing_ok=True)
        return True
    except Exception as exc:
        logger.error(f"Failed to delete snapshot {filename}: {exc}")
        return False


def list_snapshots(snapshot_dir: Path) -> dict:
    """
    Return counts and metadata for all snapshots.

    Returns:
        {
          "unlabelled": [ {filename, size_bytes, url_path}, ... ],
          "labelled": {
              "grade1": [ {filename, size_bytes}, ... ],
              ...
          },
          "counts": { "unlabelled": N, "grade1": N, ... }
        }
    """
    result: dict = {"unlabelled": [], "labelled": {}, "counts": {}}

    # Unlabelled
    unlabelled_dir = snapshot_dir / "unlabelled"
    unlabelled: list[dict] = []
    if unlabelled_dir.exists():
        for f in sorted(unlabelled_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            if f.suffix.lower() in (".jpg", ".jpeg", ".png"):
                try:
                    unlabelled.append({
                        "filename":   f.name,
                        "size_bytes": f.stat().st_size,
                    })
                except Exception:
                    pass
    result["unlabelled"] = unlabelled
    result["counts"]["unlabelled"] = len(unlabelled)

    # Labelled per grade
    for grade_key in GRADE_KEYS:
        grade_dir = snapshot_dir / "labelled" / grade_key
        imgs: list[dict] = []
        if grade_dir.exists():
            for f in sorted(grade_dir.iterdir()):
                if f.suffix.lower() in (".jpg", ".jpeg", ".png"):
                    try:
                        imgs.append({
                            "filename":   f.name,
                            "size_bytes": f.stat().st_size,
                        })
                    except Exception:
                        pass
        result["labelled"][grade_key] = imgs
        result["counts"][grade_key]   = len(imgs)

    return result
