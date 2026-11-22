"""APP-033 M1: local scan -> page-background removal -> A4 preview.

No watcher and NO PRINTING capabilities. The original is never overwritten.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_PIXELS = 45_000_000
A4_MM = (210, 297)


@dataclass
class Detection:
    status: str
    reason: str
    threshold: float | None = None
    rectangle: list[int] | None = None
    area_fraction: float | None = None
    foreground_contrast: float | None = None
    source_dpi: float | None = None
    dpi_assumed: bool = False
    rotation_degrees: int = 0
    scale_mode: str = "nominal"
    a4_orientation: str | None = None


def _load(path: Path) -> tuple[np.ndarray, float | None]:
    with Image.open(path) as opened:
        if opened.format not in {"JPEG", "PNG", "TIFF"}:
            raise ValueError("UNSUPPORTED_IMAGE_FORMAT")
        if opened.width * opened.height > MAX_PIXELS or min(opened.size) < 100:
            raise ValueError("INVALID_DIMENSIONS")
        dpi_value = opened.info.get("dpi")
        dpi = float(dpi_value[0]) if isinstance(dpi_value, tuple) else None
        if dpi is not None and not 72 <= dpi <= 1200:
            dpi = None
        # EXIF orientation is applied once on input.
        rgb = np.array(ImageOps.exif_transpose(opened).convert("RGB"))
    return rgb, dpi


def detect_and_clean(rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, Detection]:
    """Return clean RGB, paper mask, outlined RGB and conservative diagnosis."""
    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError("RGB_IMAGE_REQUIRED")
    h, w = rgb.shape[:2]
    if h * w > MAX_PIXELS or min(h, w) < 100:
        raise ValueError("INVALID_DIMENSIONS")
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    # A white scan with dark text should not be cropped artificially.
    border_width = max(5, round(min(h, w) * 0.025))
    edge_samples = np.concatenate((
        gray[:border_width].ravel(), gray[-border_width:].ravel(),
        gray[:, :border_width].ravel(), gray[:, -border_width:].ravel()
    ))
    if np.median(edge_samples) > 215 and np.mean(gray < 95) < 0.16:
        mask = np.full((h, w), 255, np.uint8)
        return rgb.copy(), mask, rgb.copy(), Detection("ACCEPT", "ALREADY_LIGHT_BACKGROUND", rectangle=[0, 0, w, h], area_fraction=1.0)

    # Ignore the narrow bright scanner/frame strip ONLY when estimating shape.
    # The output is still assembled from the full-resolution input.
    guard = max(8, round(min(h, w) * 0.015))
    blurred = cv2.GaussianBlur(gray, (7, 7), 0)
    inner = blurred.copy()
    inner[:guard] = 0
    inner[-guard:] = 0
    inner[:, :guard] = 0
    inner[:, -guard:] = 0
    threshold, _ = cv2.threshold(inner, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    threshold = float(threshold)
    bright = np.uint8(inner > threshold) * 255
    kernel_size = max(9, (round(min(h, w) * 0.027) | 1))
    close_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    joined = cv2.morphologyEx(bright, cv2.MORPH_CLOSE, close_kernel)
    joined[:guard] = 0
    joined[-guard:] = 0
    joined[:, :guard] = 0
    joined[:, -guard:] = 0
    n, labels, stats, _ = cv2.connectedComponentsWithStats(joined)
    report = Detection("HOLD", "NO_PAPER_CANDIDATE", threshold=threshold)
    mask = np.zeros((h, w), np.uint8)
    outline = rgb.copy()
    if n <= 1:
        return rgb.copy(), mask, outline, report
    order = sorted(range(1, n), key=lambda i: int(stats[i, cv2.CC_STAT_AREA]), reverse=True)
    winner = order[0]
    component_area = int(stats[winner, cv2.CC_STAT_AREA])
    if component_area < 0.06 * h * w:
        report.reason = "PAPER_TOO_SMALL_OR_DARK"
        return rgb.copy(), mask, outline, report
    if len(order) > 1 and stats[order[1], cv2.CC_STAT_AREA] > 0.18 * component_area:
        report.reason = "MULTIPLE_UNCONNECTED_CANDIDATES"
        return rgb.copy(), mask, outline, report

    component = np.uint8(labels == winner) * 255
    contours, _ = cv2.findContours(component, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    hull = cv2.convexHull(max(contours, key=cv2.contourArea))
    shape_area = cv2.contourArea(hull)
    x, y, bw, bh = cv2.boundingRect(hull)
    fill = component_area / max(1, shape_area)
    min_rect = cv2.minAreaRect(hull)
    rw, rh = min_rect[1]
    rectangularity = shape_area / max(1, rw * rh)
    report.area_fraction = round(component_area / (h * w), 4)
    report.rectangle = [x, y, bw, bh]
    if fill < 0.60 or rectangularity < 0.68:
        report.reason = "IRREGULAR_PAPER_SHAPE"
        return rgb.copy(), mask, outline, report

    # Protect all pixels inside the inferred PAPER hull, including interior
    # black illustrations, book gutter, and holes in the bright threshold map.
    cv2.fillConvexPoly(mask, hull, 255)
    expansion = max(8, round(min(h, w) * 0.012))
    disk = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * expansion + 1, 2 * expansion + 1))
    mask = cv2.dilate(mask, disk)
    # The guard trimmed scanner-white strips; recover page portions touching
    # that guard, without assuming all four image edges belong to paper.
    if x <= guard + 2:
        col = min(w - 1, guard + expansion)
        mask[:, :col] = mask[:, col:col + 1]
    if y <= guard + 2:
        row = min(h - 1, guard + expansion)
        mask[:row, :] = mask[row:row + 1, :]
    if x + bw >= w - guard - 2:
        col = max(0, w - guard - expansion - 1)
        mask[:, col + 1:] = mask[:, col:col + 1]
    if y + bh >= h - guard - 2:
        row = max(0, h - guard - expansion - 1)
        mask[row + 1:, :] = mask[row:row + 1, :]

    paper_values = gray[component > 0]
    outside_values = gray[mask == 0]
    if outside_values.size < 0.01 * h * w:
        report.reason = "INSUFFICIENT_BACKGROUND_EVIDENCE"
        return rgb.copy(), mask, outline, report
    contrast = float(np.median(paper_values) - np.median(outside_values))
    report.foreground_contrast = round(contrast, 1)
    if contrast < 28:
        report.reason = "LOW_PAGE_BACKGROUND_CONTRAST"
        return rgb.copy(), mask, outline, report
    if min(bw, bh) < 0.12 * min(h, w):
        report.reason = "IMPLAUSIBLE_PAPER_EXTENT"
        return rgb.copy(), mask, outline, report

    report.status = "ACCEPT"
    report.reason = "PAPER_BOUNDARY_DETECTED"
    cleaned = rgb.copy()
    cleaned[mask == 0] = (255, 255, 255)
    # Outline is diagnostics only; never drawn on the printable result.
    cv2.drawContours(outline, [hull], -1, (255, 35, 35), thickness=max(2, min(h, w) // 350))
    return cleaned, mask, outline, report


def _rotate(image: np.ndarray, degrees: int) -> np.ndarray:
    return np.rot90(image, (degrees // 90) % 4).copy() if degrees else image


def layout_a4(cleaned: np.ndarray, mask: np.ndarray, output_dpi: int, source_dpi: float,
              rotation: int = 0, scale_mode: str = "nominal") -> np.ndarray:
    if output_dpi not in {150, 300} or rotation not in {0, 90, 180, 270} or scale_mode not in {"nominal", "fit"}:
        raise ValueError("INVALID_OUTPUT_SETTINGS")
    ys, xs = np.where(mask > 0)
    if len(xs) == 0:
        raise ValueError("EMPTY_PAPER_MASK")
    margin_px = max(4, int(round(min(cleaned.shape[:2]) * 0.003)))
    left = max(0, int(xs.min()) - margin_px)
    right = min(cleaned.shape[1], int(xs.max()) + margin_px + 1)
    top = max(0, int(ys.min()) - margin_px)
    bottom = min(cleaned.shape[0], int(ys.max()) + margin_px + 1)
    paper = _rotate(cleaned[top:bottom, left:right], rotation)
    # Choose portrait/landscape by geometry, not inferred reading direction.
    landscape = paper.shape[1] > paper.shape[0]
    mm_w, mm_h = (297, 210) if landscape else (210, 297)
    page_w, page_h = (round(mm_w / 25.4 * output_dpi), round(mm_h / 25.4 * output_dpi))
    inset = round(5 / 25.4 * output_dpi)
    usable_w, usable_h = page_w - 2 * inset, page_h - 2 * inset
    fit_scale = min(usable_w / paper.shape[1], usable_h / paper.shape[0])
    scale = min(float(output_dpi) / source_dpi, fit_scale) if scale_mode == "nominal" else fit_scale
    # Nominal uses scan DPI (or a declared assumption); fit enlarges to paper.
    # Neither mode attempts OCR or automatically infers upright text.
    if scale <= 0:
        raise ValueError("INVALID_SCALE")
    rw, rh = max(1, round(paper.shape[1] * scale)), max(1, round(paper.shape[0] * scale))
    fitted = cv2.resize(paper, (rw, rh), interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
    canvas = np.full((page_h, page_w, 3), 255, dtype=np.uint8)
    x0, y0 = (page_w - rw) // 2, (page_h - rh) // 2
    canvas[y0:y0 + rh, x0:x0 + rw] = fitted
    # MF244dw prints monochrome. Keep intermediate RGB cleaned for inspection.
    gray = cv2.cvtColor(canvas, cv2.COLOR_RGB2GRAY)
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)


def process(path: Path, output_dir: Path, rotation: int = 0, output_dpi: int = 150,
            source_dpi: float | None = None, scale_mode: str = "nominal") -> Detection:
    if rotation not in {0, 90, 180, 270} or output_dpi not in {150, 300} or scale_mode not in {"nominal", "fit"}:
        raise ValueError("INVALID_OUTPUT_SETTINGS")
    if source_dpi is not None and not 72 <= source_dpi <= 1200:
        raise ValueError("INVALID_SOURCE_DPI")
    # Never confuse an earlier ACCEPT preview with a later HOLD result.
    # The caller must choose a fresh output directory for each scan.
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError("OUTPUT_DIRECTORY_NOT_EMPTY: choose a new --output path")
    try:
        image, embedded_dpi = _load(path)
        cleaned, mask, outlined, report = detect_and_clean(image)
        report.dpi_assumed = source_dpi is None and embedded_dpi is None
        report.source_dpi = source_dpi or embedded_dpi or 300.0
        report.rotation_degrees = rotation
        report.scale_mode = scale_mode
    except (ValueError, OSError, UnidentifiedImageError, cv2.error) as exc:
        report = Detection("HOLD", f"INPUT_ERROR:{type(exc).__name__}")
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "report.json").write_text(json.dumps(asdict(report), ensure_ascii=False, indent=2), encoding="utf-8")
        return report
    output_dir.mkdir(parents=True, exist_ok=True)
    Image.fromarray(outlined).save(output_dir / "boundary_overlay.png")
    Image.fromarray(mask).save(output_dir / "paper_mask.png")
    if report.status == "ACCEPT":
        Image.fromarray(cleaned).save(output_dir / "cleaned.png")
        ys, xs = np.where(mask > 0)
        crop_landscape = (int(xs.max()) - int(xs.min())) > (int(ys.max()) - int(ys.min()))
        report.a4_orientation = "landscape" if crop_landscape != (rotation in {90, 270}) else "portrait"
        preview = layout_a4(cleaned, mask, output_dpi, report.source_dpi, rotation, scale_mode)
        Image.fromarray(preview).save(output_dir / "a4_preview.png", dpi=(output_dpi, output_dpi))
    (output_dir / "report.json").write_text(json.dumps(asdict(report), ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="M1 only: detect page, whiten outer background and make an A4 preview. NEVER prints.")
    parser.add_argument("input", type=Path, help="Local JPEG/PNG/TIFF scan")
    parser.add_argument("--output", type=Path, default=Path("m1_output"))
    parser.add_argument("--rotate", type=int, choices=(0, 90, 180, 270), default=0)
    parser.add_argument("--output-dpi", type=int, choices=(150, 300), default=150)
    parser.add_argument("--source-dpi", type=float, help="If scan metadata lacks DPI, set a calibrated value; default assumes 300 DPI")
    parser.add_argument("--scale-mode", choices=("nominal", "fit"), default="nominal",
                        help="nominal: do not enlarge beyond source physical size; fit: fill A4 printable area")
    args = parser.parse_args()
    if args.input.resolve().is_relative_to(args.output.resolve()):
        parser.error("Input must not be inside the output directory")
    result = process(args.input, args.output, args.rotate, args.output_dpi, args.source_dpi, args.scale_mode)
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    return 0 if result.status == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
