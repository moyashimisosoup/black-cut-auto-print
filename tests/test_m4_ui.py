"""M4 GUI smoke tests. Run with Xvfb on Linux; no real printing."""
import sys
import time
from pathlib import Path

from PIL import Image
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import m2_monitor
from m4_operator_ui import OperatorApp, preview_history


def test_history_query_is_readonly(tmp_path):
    folder = tmp_path / "out"
    store = m2_monitor.JobStore(folder / "jobs.sqlite3")
    job = store.claim("test-fingerprint", tmp_path / "synthetic.jpg")
    assert job
    store.set(job, "READY_REVIEW", "DRY_RUN_NO_PRINT")
    store.close()
    records = preview_history(folder)
    assert len(records) == 1
    assert records[0]["state"] == "READY_REVIEW"
    assert preview_history(tmp_path / "missing") == []


def test_window_starts_disarmed_and_can_preview_synthetic_jpeg(monkeypatch, tmp_path):
    """This is a real Tk event-loop + folder monitor, but sender is never used."""
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    output = tmp_path / "out"
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))

    def fake_image_processing(src, folder, **kwargs):
        folder.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (1240, 1754), "white").save(folder / "a4_preview.png")
        return type("FakeDetection", (), {"status": "ACCEPT", "reason": "SYNTHETIC_OK"})()

    monkeypatch.setattr(m2_monitor, "process", fake_image_processing)
    app = OperatorApp()
    app.withdraw()
    try:
        assert not app.gate.armed
        assert app.arm_button.instate(["disabled"])
        app.inbox.set(str(inbox))
        app.output.set(str(output))
        app._start()
        assert app.worker is not None
        time.sleep(0.2)
        Image.new("RGB", (200, 250), "white").save(inbox / "new.jpg", "JPEG")
        deadline = time.monotonic() + 9
        detected = False
        while time.monotonic() < deadline:
            app.update()
            if any(r["state"] == "READY_REVIEW" for r in app.rows_by_id.values()):
                detected = True
                break
            time.sleep(0.1)
        assert detected, "GUI did not receive and process new synthetic JPEG"
        assert not app.gate.armed
        assert "OFF" in app.permission.get()
        assert (next(iter(output.glob("jobs/*/a4_preview.png")))).is_file()
        app._stop()
        deadline = time.monotonic() + 4
        while app.worker and app.worker.is_alive() and time.monotonic() < deadline:
            app.update()
            time.sleep(0.05)
        assert not app.worker.is_alive()
    finally:
        app._close()
        # Flush scheduled UI callbacks only if the window still exists.
        try:
            app.update()
        except Exception:
            pass
