"""The final auto-print gate: valid preview, configured trim, ONE mocked job."""
from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from m2_monitor import JobStore, ScanPipeline
from print_preflight import PreviewMismatch, check_preview_for_print
from printer_preferences import prefer_canon_queue


def _approved_preview(tmp_path: Path, **overrides) -> Path:
    root = tmp_path / "existing" / "jobs" / "abc"
    root.mkdir(parents=True, exist_ok=True)
    preview = root / "a4_preview.png"
    Image.new("RGB", (1240, 1754), "white").save(preview)
    report = dict(status="ACCEPT", rotation_degrees=90, source_dpi=300.0,
                  scale_mode="fit", trim_mm=3.0, trim_pixels=35,
                  a4_orientation="landscape")
    report.update(overrides)
    (root / "report.json").write_text(json.dumps(report), encoding="utf-8")
    return preview


def test_preview_fingerprint_requires_same_rotation_scale_dpi_and_trim(tmp_path):
    p = _approved_preview(tmp_path)
    check_preview_for_print(p, rotation=90, dpi=300, scale_mode="fit", trim_mm=3)
    for values in (
        dict(rotation=0, dpi=300, scale_mode="fit", trim_mm=3),
        dict(rotation=90, dpi=600, scale_mode="fit", trim_mm=3),
        dict(rotation=90, dpi=300, scale_mode="nominal", trim_mm=3),
        dict(rotation=90, dpi=300, scale_mode="fit", trim_mm=5)
    ):
        with pytest.raises(PreviewMismatch):
            check_preview_for_print(p, **values)


def test_preflight_rejects_missing_metadata_and_skipped_trim(tmp_path):
    p = _approved_preview(tmp_path)
    p.with_name("report.json").unlink()
    with pytest.raises(PreviewMismatch, match="旧版"):
        check_preview_for_print(p, rotation=90, dpi=300, scale_mode="fit", trim_mm=3)
    p = _approved_preview(tmp_path, trim_pixels=0,
                          trim_warning="TRIM_SKIPPED_NO_PAPER_BOUNDARY")
    with pytest.raises(PreviewMismatch, match="適用されなかった"):
        check_preview_for_print(p, rotation=90, dpi=300, scale_mode="fit", trim_mm=3)


def test_actual_cropping_pipeline_sends_one_mocked_print_and_no_repeat(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    source = inbox / "brand-new.jpg"
    scan = np.full((900, 700, 3), 38, dtype=np.uint8)
    scan[90:820, 88:615] = (226, 230, 225)
    scan[300:440, 340:500] = (20, 25, 22)
    Image.fromarray(scan).save(source, format="JPEG")

    calls: list[tuple[Path, str]] = []
    def sender(preview: Path, printer: str) -> int:
        calls.append((preview, printer))
        assert preview.is_file()
        with Image.open(preview) as im:
            assert im.width > im.height  # rotated scan -> landscape A4
        return 743

    output = tmp_path / "result"
    store = JobStore(output / "jobs.sqlite3")
    try:
        pipeline = ScanPipeline(store, output, printer="Canon MF244dw",
                                armed=True, sender=sender, source_dpi=300,
                                rotate=90, trim_mm=3, scale_mode="fit")
        assert pipeline.run_one(source) == "SUBMITTED"
        assert pipeline.run_one(source) == "DUPLICATE"
        assert len(calls) == 1
        job = store.rows()[0]
        assert job["state"] == "SUBMITTED" and job["spool_id"] == "743"
        report = json.loads((output / "jobs" / job["id"] / "report.json").read_text())
        assert report["trim_mm"] == 3
        assert report["scale_mode"] == "fit"
        assert report["rotation_degrees"] == 90
    finally:
        store.close()


def test_auto_print_is_revoked_on_stop_before_spooler(tmp_path):
    source = tmp_path / "scan.jpg"
    scan = np.full((900, 700, 3), 35, dtype=np.uint8)
    scan[90:820, 90:615] = (220, 220, 218)
    Image.fromarray(scan).save(source)
    output = tmp_path / "results"
    stopped = threading.Event()
    stopped.set()
    calls = []
    store = JobStore(output / "jobs.sqlite3")
    try:
        p = ScanPipeline(store, output, printer="Canon MF244dw",
                         armed=True, sender=lambda *_: calls.append(1),
                         stop=stopped, trim_mm=2, source_dpi=300)
        assert p.run_one(source) == "HOLD"
        assert not calls
        assert store.rows()[0]["message"] == "MONITOR_STOPPED_BEFORE_SUBMISSION"
    finally:
        store.close()


def test_canon_preference_is_not_arbitrary():
    names = ["Microsoft Print to PDF", "Canon MF240 Series", "Other printer"]
    assert prefer_canon_queue(names) == "Canon MF240 Series"
    assert prefer_canon_queue(names, "Other printer") == "Other printer"
    assert prefer_canon_queue(names, "Missing printer") == "Canon MF240 Series"
    assert prefer_canon_queue(["Microsoft Print to PDF"]) == ""
    assert prefer_canon_queue(["Canon MF244dw", "Canon MF240 Series"]) == ""
