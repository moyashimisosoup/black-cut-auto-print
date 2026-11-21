"""Synthetic-only tests. Do not commit copyrighted scan samples."""
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from m1_processing import detect_and_clean, layout_a4, process


def make_scan(borders=(55, 55, 55, 55), tint=(233, 236, 231), white_rim=False):
    # Borders are top, bottom, left, right.
    h, w = 540, 420
    image = np.zeros((h, w, 3), np.uint8)
    yy, xx = np.indices((h, w))
    shade = np.uint8(np.clip(62 + (yy / 80) + 9 * np.sin(xx / 45), 10, 110))
    image[:] = np.stack((shade, shade, shade), axis=2)
    top, bottom, left, right = borders
    y0, y1 = top, h - bottom
    x0, x1 = left, w - right
    if x0 >= x1 or y0 >= y1:
        return image
    image[y0:y1, x0:x1] = tint
    cv2.rectangle(image, (x0 + 12, y0 + 12), (x0 + 85, y0 + 60), (12, 12, 12), -1)
    # Colored illustrations, dark details and a narrow book gutter.
    cv2.line(image, (x0 + 100, y0 + 18), (x1 - 14, y1 - 20), (50, 120, 175), 3)
    if y1 - y0 > 180:
        cv2.line(image, ((x0 + x1) // 2, y0 + 4), ((x0 + x1) // 2, y1 - 4), (61, 65, 63), 5)
    if white_rim:
        image[:4] = 255
        image[-4:] = 255
        image[:, :4] = 255
        image[:, -4:] = 255
    return image


def test_each_side_and_four_sides():
    sides = [(0, 0, 0, 90), (0, 0, 90, 0), (0, 100, 0, 0), (80, 0, 0, 0), (70, 60, 80, 65)]
    for borders in sides:
        image = make_scan(borders)
        cleaned, mask, _, d = detect_and_clean(image)
        assert d.status == 'ACCEPT', (borders, d)
        assert np.all(cleaned[250, 200] == image[250, 200]), borders
        t, b, l, r = borders
        if t: assert (cleaned[0, 200] == [255, 255, 255]).all()
        if b: assert (cleaned[539, 200] == [255, 255, 255]).all()
        if l: assert (cleaned[260, 0] == [255, 255, 255]).all()
        if r: assert (cleaned[260, 419] == [255, 255, 255]).all()
        # No color remapping of the paper's dark illustration.
        assert (cleaned[t + 30, l + 30] == [12, 12, 12]).all(), borders


def test_white_rim_yellowed_paper_and_gutter():
    image = make_scan((58, 45, 44, 75), tint=(222, 208, 155), white_rim=True)
    cleaned, mask, _, d = detect_and_clean(image)
    assert d.status == 'ACCEPT', d
    assert np.all(cleaned[260, 180] == image[260, 180])
    assert (cleaned[240, 400] == [255, 255, 255]).all()


def test_dark_ambiguous_scan_must_hold():
    image = np.full((540, 420, 3), 57, dtype=np.uint8)
    cleaned, mask, _, d = detect_and_clean(image)
    assert d.status == 'HOLD'


def test_white_image_is_pass_through():
    image = np.full((540, 420, 3), 251, dtype=np.uint8)
    cv2.putText(image, 'safe', (130, 230), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (10, 10, 10), 3)
    cleaned, mask, _, d = detect_and_clean(image)
    assert d.status == 'ACCEPT' and d.reason == 'ALREADY_LIGHT_BACKGROUND'
    assert np.array_equal(cleaned, image)


def test_a4_rotation_and_centering():
    image = make_scan((60, 60, 55, 55))
    cleaned, mask, _, d = detect_and_clean(image)
    assert d.status == 'ACCEPT'
    page = layout_a4(cleaned, mask, 150, 300, 90)
    assert page.shape[1] > page.shape[0], page.shape
    assert (page[10, 10] == [255, 255, 255]).all()


def test_damaged_file_returns_hold(tmp_path):
    damaged = tmp_path / 'damaged.jpg'
    damaged.write_bytes(b'not a jpeg')
    result = process(damaged, tmp_path / 'output')
    assert result.status == 'HOLD'
    assert (tmp_path / 'output' / 'report.json').exists()
    assert not (tmp_path / 'output' / 'a4_preview.png').exists()


def test_written_preview_has_no_print_side_effect(tmp_path):
    input_file = tmp_path / 'synthetic.png'
    Image.fromarray(make_scan((70, 60, 65, 70))).save(input_file)
    folder = tmp_path / 'out'
    result = process(input_file, folder, rotation=0, output_dpi=150)
    assert result.status == 'ACCEPT'
    assert (folder / 'boundary_overlay.png').exists()
    assert (folder / 'paper_mask.png').exists()
    assert (folder / 'cleaned.png').exists()
    assert (folder / 'a4_preview.png').exists()
    assert (folder / 'report.json').exists()

def test_existing_output_is_never_reused(tmp_path):
    input_file = tmp_path / "sample.png"
    Image.fromarray(make_scan()).save(input_file)
    folder = tmp_path / "out"
    assert process(input_file, folder).status == "ACCEPT"
    import pytest
    with pytest.raises(FileExistsError, match="OUTPUT_DIRECTORY_NOT_EMPTY"):
        process(input_file, folder)
