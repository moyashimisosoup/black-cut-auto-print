"""M2 tests run without Windows, printer hardware, or real user scans."""
import sqlite3
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import m2_monitor as m2
from windows_print import _check_a4


def jpeg(folder: Path, filename: str) -> Path:
    image = folder / filename
    Image.new("RGB", (200, 240), "white").save(image, format="JPEG")
    return image


def store_and_pipeline(tmp_path, monkeypatch, *, armed=False, sender=None, stop=None, hold=False):
    store = m2.JobStore(tmp_path / "results" / "jobs.sqlite3")
    called = []

    def fake_process(src, output, **kwargs):
        called.append((src.name, kwargs))
        output.mkdir(parents=True, exist_ok=True)
        if hold:
            return SimpleNamespace(status="HOLD", reason="UNCERTAIN_PAPER_BOUNDARY")
        Image.new("RGB", (248, 351), "white").save(output / "a4_preview.png")
        return SimpleNamespace(status="ACCEPT", reason="PAPER_BOUNDARY_DETECTED")

    monkeypatch.setattr(m2, "process", fake_process)
    pipeline = m2.ScanPipeline(store, tmp_path / "results",
                               printer="Canon MF240 Series",
                               armed=armed, sender=sender,
                               stop=stop)
    return store, pipeline, called


def test_old_files_are_never_processed(monkeypatch, tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    jpeg(inbox, "old.jpg")
    store, pipe, called = store_and_pipeline(tmp_path, monkeypatch)
    mon = m2.InboxMonitor(inbox, pipe, settle_seconds=1)
    assert mon.poll_once(now=0) == []
    assert mon.poll_once(now=5) == []
    assert not store.rows() and not called
    store.close()


def test_new_scan_stabilizes_dry_run_no_print(monkeypatch, tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    store, pipe, called = store_and_pipeline(tmp_path, monkeypatch)
    mon = m2.InboxMonitor(inbox, pipe, settle_seconds=2)
    jpeg(inbox, "new.jpg")
    assert mon.poll_once(now=10) == []
    assert mon.poll_once(now=11) == []
    assert mon.poll_once(now=12.1) == [("new.jpg", "READY_REVIEW")]
    assert mon.poll_once(now=15) == []
    assert len(called) == 1
    assert [r["state"] for r in store.rows()] == ["READY_REVIEW"]
    store.close()


def test_two_equal_pages_are_two_distinct_scans(monkeypatch, tmp_path):
    store, pipe, called = store_and_pipeline(tmp_path, monkeypatch)
    a, b = jpeg(tmp_path, "one.jpg"), jpeg(tmp_path, "two.jpg")
    assert pipe.run_one(a) == "READY_REVIEW"
    assert pipe.run_one(b) == "READY_REVIEW"
    assert pipe.run_one(a) == "DUPLICATE"
    assert len(store.rows()) == 2 and len(called) == 2
    store.close()


def test_armed_scan_submits_only_once(monkeypatch, tmp_path):
    send_calls = []

    def sender(preview, printer):
        send_calls.append((preview, printer))
        return 42

    store, pipe, _ = store_and_pipeline(tmp_path, monkeypatch, armed=True, sender=sender)
    source = jpeg(tmp_path, "test.jpg")
    assert pipe.run_one(source) == "SUBMITTED"
    assert pipe.run_one(source) == "DUPLICATE"
    assert len(send_calls) == 1
    assert store.rows()[0]["spool_id"] == "42"
    assert store.rows()[0]["message"] == "SPOOLER_ACCEPTED_NOT_PAPER_VERIFIED"
    store.close()


def test_ambiguous_print_failure_becomes_unknown(monkeypatch, tmp_path):
    def broken(_preview, _printer):
        raise IOError("spooler uncertain")

    store, pipe, _ = store_and_pipeline(tmp_path, monkeypatch, armed=True, sender=broken)
    src = jpeg(tmp_path, "test.jpg")
    assert pipe.run_one(src) == "UNKNOWN"
    assert store.rows()[0]["state"] == "UNKNOWN"
    store.close()
    reopened = m2.JobStore(tmp_path / "results" / "jobs.sqlite3")
    assert reopened.rows()[0]["state"] == "UNKNOWN"
    reopened.close()


def test_crash_during_submitting_recovers_as_unknown(monkeypatch, tmp_path):
    store, pipe, _ = store_and_pipeline(tmp_path, monkeypatch)
    job = store.claim("stable-id", jpeg(tmp_path, "test.jpg"))
    assert job is not None
    store.set(job, "SUBMITTING", "preflight committed")
    store.close()
    recovered = m2.JobStore(tmp_path / "results" / "jobs.sqlite3")
    assert recovered.rows()[0]["state"] == "UNKNOWN"
    recovered.close()


def test_uncertain_page_remains_hold(monkeypatch, tmp_path):
    store, pipe, _ = store_and_pipeline(tmp_path, monkeypatch, hold=True)
    assert pipe.run_one(jpeg(tmp_path, "scan.jpg")) == "HOLD"
    assert store.rows()[0]["message"] == "UNCERTAIN_PAPER_BOUNDARY"
    store.close()


def test_stopping_before_submit_prevents_print(monkeypatch, tmp_path):
    stop = threading.Event()
    stop.set()
    calls = []
    store, pipe, _ = store_and_pipeline(tmp_path, monkeypatch,
                                        armed=True, sender=lambda a, b: calls.append(1),
                                        stop=stop)
    assert pipe.run_one(jpeg(tmp_path, "scan.jpg")) == "HOLD"
    assert not calls
    assert store.rows()[0]["message"] == "MONITOR_STOPPED_BEFORE_SUBMISSION"
    store.close()


def test_incomplete_jpeg_is_not_processed(monkeypatch, tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    store, pipe, called = store_and_pipeline(tmp_path, monkeypatch)
    mon = m2.InboxMonitor(inbox, pipe, settle_seconds=1, timeout_seconds=4)
    (inbox / "partial.jpg").write_bytes(b"unfinished jpeg")
    assert mon.poll_once(now=0) == []
    assert mon.poll_once(now=2) == []
    assert not called
    assert mon.poll_once(now=5) == [("partial.jpg", "STABILIZATION_TIMEOUT_HOLD")]
    store.close()


def test_a4_dimensions_and_invalid_layout():
    assert _check_a4(2480, 3508)
    assert _check_a4(3508, 2480)
    assert not _check_a4(1000, 1000)
    assert not _check_a4(320, 440)


def test_output_inbox_is_rejected(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    assert not m2._paths_safe(inbox, inbox)
    assert not m2._paths_safe(inbox, inbox / "output")
    assert not m2._paths_safe(inbox, tmp_path)


def test_cli_refuses_unreviewed_arming():
    with pytest.raises(SystemExit) as e:
        m2.run_cli(["--arm-printing", "--inbox", ".", "--output", "out"])
    assert e.value.code == 2
