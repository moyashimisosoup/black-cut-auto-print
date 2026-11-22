"""Synthetic-only direct-consent and recoverable scan cleanup tests."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from m2_monitor import JobStore, ScanPipeline, source_fingerprint
from m4_print_gate import GateError, PrintGate
from source_cleanup import recycle_scanned_source, spooler_print_status


def test_direct_consent_skips_manual_proof_but_requires_explicit_ack():
    gate = PrintGate()
    assert not gate.will_submit("Canon MF240 Series")
    with pytest.raises(GateError, match="DIRECT_PRINT_ACKNOWLEDGEMENT_REQUIRED"):
        gate.arm_without_trial("Canon MF240 Series", explicit_confirmation=True,
                               acknowledge_unverified=False)
    with pytest.raises(GateError, match="DIRECT_PRINT_ACKNOWLEDGEMENT_REQUIRED"):
        gate.arm_without_trial("Canon MF240 Series", explicit_confirmation=False,
                               acknowledge_unverified=True)
    gate.arm_without_trial("Canon MF240 Series", explicit_confirmation=True,
                           acknowledge_unverified=True)
    assert gate.will_submit("Canon MF240 Series")
    assert gate.verified_printer is None
    assert not gate.will_submit("Other")
    gate.disarm()
    assert not gate.will_submit("Canon MF240 Series")
    assert gate.direct_authorized_printer is None
    with pytest.raises(GateError, match="PHYSICAL_TRIAL"):
        gate.arm("Canon MF240 Series", explicit_confirmation=True)


def test_direct_consent_fails_during_inflight_manual_proof(tmp_path):
    preview = tmp_path / "a4_preview.png"
    preview.write_bytes(b"synthetic")
    gate = PrintGate()
    gate.begin_manual_test("Canon MF240 Series", preview)
    with pytest.raises(GateError, match="TEST_NOT_VERIFIED"):
        gate.arm_without_trial("Canon MF240 Series", explicit_confirmation=True,
                               acknowledge_unverified=True)
    gate.manual_failed()


def _synthetic_scan(path):
    Image.new("RGB", (250, 320), "white").save(path, "JPEG")


def test_printed_job_recycles_only_newly_scanned_source(tmp_path, monkeypatch):
    import m2_monitor

    inbox = tmp_path / "inbox"
    inbox.mkdir()
    source = inbox / "new.jpg"
    _synthetic_scan(source)
    output = tmp_path / "results"
    calls = []
    status = ["PENDING", "PRINTED"]
    recycled = []
    def fake_process(_src, folder, **_kwargs):
        folder.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (1240, 1754), "white").save(folder / "a4_preview.png")
        return type("Fake", (), {"status": "ACCEPT"})()
    monkeypatch.setattr(m2_monitor, "process", fake_process)
    def fake_recycler(src, received, fingerprint):
        assert src == source and received == inbox
        assert fingerprint == source_fingerprint(source)
        recycled.append(src.name)
        src.unlink()
        return "SOURCE_RECYCLED"

    store = JobStore(output / "jobs.sqlite3")
    try:
        pipeline = ScanPipeline(
            store, output, printer="Canon MF240 Series",
            armed=True, inbox=inbox, recycle_after_print=True,
            sender=lambda _path, _printer: 44,
            completion_checker=lambda *_: status.pop(0),
            recycler=fake_recycler)
        assert pipeline.run_one(source) == "SUBMITTED"
        assert source.exists() and not recycled  # GDI submission is NOT printing.
        assert pipeline.poll_cleanup() == []  # Still queued, retain JPEG.
        assert source.exists()
        assert pipeline.poll_cleanup() == [("new.jpg", "SOURCE_RECYCLED")]
        assert not source.exists()
        assert recycled == ["new.jpg"]
        assert store.rows()[0]["state"] == "SPOOLER_PRINTED"
        assert not pipeline.pending_cleanup
    finally:
        store.close()


@pytest.mark.parametrize("reported", ["UNKNOWN", "FAILED"])
def test_unknown_print_keeps_original(tmp_path, monkeypatch, reported):
    import m2_monitor
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    source = inbox / "scan.jpg"
    _synthetic_scan(source)
    def fake_process(_src, folder, **_kwargs):
        folder.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (1240, 1754), "white").save(folder / "a4_preview.png")
        return type("Fake", (), {"status": "ACCEPT"})()
    monkeypatch.setattr(m2_monitor, "process", fake_process)
    out = tmp_path / "out"
    store = JobStore(out / "jobs.sqlite3")
    try:
        p = ScanPipeline(store, out, printer="Canon MF240 Series", armed=True,
                         sender=lambda *_: 100, inbox=inbox, recycle_after_print=True,
                         completion_checker=lambda *_: reported,
                         recycler=lambda *_: pytest.fail("unexpected cleanup"))
        assert p.run_one(source) == "SUBMITTED"
        assert p.poll_cleanup() == [("scan.jpg", "PRINT_UNCONFIRMED_SOURCE_RETAINED")]
        assert source.exists()
        assert store.rows()[0]["state"] == "SUBMITTED"
    finally:
        store.close()


def test_safe_recycle_rejects_modified_or_outside_source(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    src = inbox / "paper.jpg"
    _synthetic_scan(src)
    original = source_fingerprint(src)
    src.write_bytes(b"modified")
    assert recycle_scanned_source(src, inbox, original, trash=lambda _: pytest.fail("must retain")) == "SOURCE_CHANGED_RETAINED"
    outside = tmp_path / "outside.jpg"
    _synthetic_scan(outside)
    assert recycle_scanned_source(outside, inbox, source_fingerprint(outside),
                                  trash=lambda _: pytest.fail("must retain")) == "SOURCE_UNSAFE_RETAINED"
    assert src.exists() and outside.exists()


def test_recycle_moves_direct_inbox_file_without_hard_delete(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    src = inbox / "scan.jpg"
    _synthetic_scan(src)
    recycled = tmp_path / "recycle-bin.jpg"
    def fake_trash(file):
        Path(file).rename(recycled)
    assert recycle_scanned_source(src, inbox, source_fingerprint(src),
                                  trash=fake_trash) == "SOURCE_RECYCLED"
    assert not src.exists() and recycled.exists()


def test_print_status_unavailable_is_not_assumed_success():
    # CI runs on Linux; the Windows status adapter must never guess.
    if sys.platform != "win32":
        assert spooler_print_status("Canon MF240 Series", 42) == "UNKNOWN"
