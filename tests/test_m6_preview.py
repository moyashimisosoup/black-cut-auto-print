"""M6 synthetic-only orientation, A4 sizing and safe preview reprocessing tests."""
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from m1_processing import layout_a4, process
from m2_monitor import JobStore
from m6_preview import reprocess_preview


def original_scan():
    image = np.full((540, 420, 3), 45, dtype=np.uint8)
    image[45:500, 52:368] = (230, 228, 220)
    cv2.rectangle(image, (75, 85), (142, 145), (23, 23, 23), -1)
    cv2.putText(image, "TEST", (120, 280), cv2.FONT_HERSHEY_SIMPLEX, 1,
                (30, 30, 30), 3)
    return image


def test_nominal_and_fit_differ_but_use_correct_a4_landscape():
    scan = original_scan()
    mask = np.zeros(scan.shape[:2], dtype=np.uint8)
    mask[45:500, 52:368] = 255
    nominal = layout_a4(scan, mask, 300, 300, rotation=90)
    fit = layout_a4(scan, mask, 300, 300, rotation=90, scale_mode="fit")
    assert nominal.shape == fit.shape
    assert nominal.shape[1] > nominal.shape[0]  # after 90-degree rotation
    assert (nominal[10, 10] == 255).all()
    assert (fit[10, 10] == 255).all()
    nominal_pixels = np.count_nonzero(np.any(nominal < 245, axis=2))
    fit_pixels = np.count_nonzero(np.any(fit < 245, axis=2))
    assert fit_pixels > nominal_pixels * 4


def test_preview_reprocessing_is_not_a_print_and_old_job_is_untouched(tmp_path, monkeypatch):
    source = tmp_path / "scan.jpg"
    Image.fromarray(original_scan()).save(source, format="JPEG")
    output = tmp_path / "results"
    store = JobStore(output / "jobs.sqlite3")
    old = store.claim("ORIGINAL_SCAN", source)
    store.set(old, "READY_REVIEW", "ORIGINAL_NOT_PRINTED")
    store.close()

    # Any attempt to load a printer here is a hard failure.
    import windows_print
    monkeypatch.setattr(windows_print, "submit_a4",
                        lambda *_args, **_kwargs: pytest.fail("unexpected print"))

    first_state, first = reprocess_preview(source, output, rotation=90,
                                           source_dpi=300, scale_mode="fit", trim_mm=1)
    assert first_state == "READY_REVIEW"
    with Image.open(output / "jobs" / first / "a4_preview.png") as preview:
        assert preview.width > preview.height
    report = json.loads((output / "jobs" / first / "report.json").read_text())
    assert report["rotation_degrees"] == 90
    assert report["scale_mode"] == "fit"
    assert report["trim_mm"] == 1.0
    assert report["a4_orientation"] == "landscape"

    second_state, second = reprocess_preview(source, output, rotation=270,
                                             source_dpi=300, scale_mode="nominal")
    assert second_state == "READY_REVIEW"
    assert second != first
    store = JobStore(output / "jobs.sqlite3")
    rows = store.rows()
    store.close()
    assert len(rows) == 3
    assert {r["id"] for r in rows} == {old, first, second}
    assert next(r for r in rows if r["id"] == old)["message"] == "ORIGINAL_NOT_PRINTED"
    assert all(r["state"] == "READY_REVIEW" for r in rows)
    assert all(r["spool_id"] is None for r in rows)


def test_invalid_or_missing_source_never_creates_a_job(tmp_path):
    output = tmp_path / "output"
    output.mkdir()
    with pytest.raises(ValueError, match="SOURCE_NOT_AVAILABLE"):
        reprocess_preview(tmp_path / "missing.jpg", output,
                          rotation=90, source_dpi=300)
    assert not (output / "jobs.sqlite3").exists()


def test_process_report_contains_explicit_orientation_without_ocr(tmp_path):
    source = tmp_path / "scan.png"
    Image.fromarray(original_scan()).save(source)
    report = process(source, tmp_path / "result", rotation=90,
                     output_dpi=150, source_dpi=300, scale_mode="nominal")
    assert report.status == "ACCEPT"
    assert report.rotation_degrees == 90
    assert report.a4_orientation == "landscape"
    assert report.scale_mode == "nominal"


def test_bad_scale_setting_is_rejected():
    with pytest.raises(ValueError, match="INVALID_OUTPUT_SETTINGS"):
        layout_a4(np.zeros((500, 400, 3), dtype=np.uint8),
                  np.ones((500, 400), dtype=np.uint8),
                  300, 300, scale_mode="stretch")
