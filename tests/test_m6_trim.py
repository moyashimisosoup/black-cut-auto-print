"""APP-033 M6 trim presets: synthetic images only, printer never connected."""
from __future__ import annotations
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from m1_processing import detect_and_clean, process, trim_paper_edges


def page_scan():
    """A synthetic full-size page and dark margins on all four sides."""
    image = np.full((1600, 1200, 3), 35, dtype=np.uint8)
    image[180:1420, 170:1030] = (229, 230, 230)
    # A narrow printed marker near the edge is intentionally clipped by 3mm.
    image[760:850, 175:190] = (16, 16, 16)
    # Central dark illustration must always be preserved.
    image[700:820, 500:660] = (15, 15, 15)
    return image


def test_mm_trim_shrinks_all_four_edges_but_keeps_center(tmp_path):
    scan = page_scan()
    source = tmp_path / "original.png"
    Image.fromarray(scan).save(source)
    plain = process(source, tmp_path / "plain", source_dpi=300, trim_mm=0)
    deep = process(source, tmp_path / "deep", source_dpi=300, trim_mm=3)
    assert plain.status == deep.status == "ACCEPT"
    assert deep.trim_pixels == round(3 / 25.4 * 300)
    assert deep.trim_warning == "EDGE_CONTENT_MAY_BE_REMOVED"
    m0 = cv2.imread(str(tmp_path / "plain" / "paper_mask.png"), cv2.IMREAD_GRAYSCALE)
    m1 = cv2.imread(str(tmp_path / "deep" / "paper_mask.png"), cv2.IMREAD_GRAYSCALE)
    assert m1.sum() < m0.sum()
    assert m0[800, 180] == 255
    assert m1[800, 180] == 0
    assert m1[760, 550] == 255
    assert m1[200, 550] == 0
    assert m1[1410, 550] == 0
    assert m1[800, 180] == 0  # left
    assert m1[800, 1025] == 0  # right
    with Image.open(tmp_path / "deep" / "cleaned.png") as image:
        pixels = np.array(image)
    assert (pixels[800, 180] == 255).all() and (pixels[760, 550] < 40).all()
    assert (tmp_path / "deep" / "trim_boundary_overlay.png").exists()
    report = json.loads((tmp_path / "deep" / "report.json").read_text())
    assert report["trim_mm"] == 3.0


def test_preset_zero_matches_unchanged_legacy_mask():
    image = page_scan()
    baseline, mask, _, original = detect_and_clean(image)
    assert original.status == "ACCEPT"
    identical, px, fraction = trim_paper_edges(mask, trim_mm=0, source_dpi=300)
    assert px == 0 and fraction == 1
    assert np.array_equal(identical, mask)
    assert np.array_equal(baseline, image * (mask[..., None] > 0) +
                          255 * (mask[..., None] == 0))


def test_aggressive_trim_holds_when_page_is_too_small(tmp_path):
    image = np.full((540, 420, 3), 35, dtype=np.uint8)
    image[55:485, 55:365] = 232
    source = tmp_path / "tiny.png"
    Image.fromarray(image).save(source)
    report = process(source, tmp_path / "too_deep", source_dpi=600, trim_mm=5)
    assert report.status == "HOLD"
    assert report.reason == "TRIM_REMOVES_TOO_MUCH_PAPER"
    assert not (tmp_path / "too_deep" / "a4_preview.png").exists()


def test_light_background_is_preserved_when_no_paper_boundary(tmp_path):
    light = np.full((650, 500, 3), 252, dtype=np.uint8)
    source = tmp_path / "plain.png"
    Image.fromarray(light).save(source)
    report = process(source, tmp_path / "out", source_dpi=300, trim_mm=5)
    assert report.status == "ACCEPT"
    assert report.trim_warning == "TRIM_SKIPPED_NO_PAPER_BOUNDARY"
    assert report.trim_pixels == 0


def test_invalid_trim_is_rejected_before_writing(tmp_path):
    scan = tmp_path / "source.png"
    Image.fromarray(page_scan()).save(scan)
    with pytest.raises(ValueError, match="INVALID_TRIM_SETTINGS"):
        process(scan, tmp_path / "destination", trim_mm=10)
    assert not (tmp_path / "destination").exists()
