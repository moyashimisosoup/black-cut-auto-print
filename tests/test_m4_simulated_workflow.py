"""Fully simulated physical acknowledgement -> armed scan -> mocked spooler.

THIS TEST NEVER SENDS ANY PRINT JOB. It only tests UI wiring and state gates.
"""
import sys
import time
from pathlib import Path

import pytest
from PIL import Image
from tkinter import messagebox

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import m2_monitor
import windows_print
from m4_operator_ui import OperatorApp


def pump_until(app, predicate, seconds=8):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.update()
        if predicate():
            return True
        time.sleep(0.05)
    return False


def test_mocked_manual_proof_then_auto_submit(monkeypatch, tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    output = tmp_path / "output"
    output.mkdir()
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    image = output / "jobs" / "manual" / "a4_preview.png"
    image.parent.mkdir(parents=True)
    Image.new("RGB", (1240, 1754), "white").save(image)

    store = m2_monitor.JobStore(output / "jobs.sqlite3")
    job = store.claim("synthetic-ready-preview", tmp_path / "sample-source.jpg")
    store.set(job, "READY_REVIEW", "TEST_ONLY", str(image))
    store.close()

    def fake_processing(_source, folder, **_kwargs):
        folder.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (1240, 1754), "white").save(folder / "a4_preview.png")
        return type("Result", (), {"status": "ACCEPT", "reason": "SYNTHETIC"})()

    sent = []

    def fake_send(path, printer):
        sent.append((str(path), printer))
        return 999

    monkeypatch.setattr(m2_monitor, "process", fake_processing)
    monkeypatch.setattr(windows_print, "list_printers", lambda: ["Canon MF244dw"])
    monkeypatch.setattr(windows_print, "submit_a4", fake_send)
    # Simulates test operator clicking "yes"; not actual paper evidence.
    monkeypatch.setattr(messagebox, "askyesno", lambda *args, **kwargs: True)

    app = OperatorApp()
    app.withdraw()
    try:
        app.inbox.set(str(inbox))
        app.output.set(str(output))
        app.printer.set("Canon MF244dw")
        app._refresh_history()
        app.tree.selection_set(job)
        # Initial state must never submit just because a preview exists.
        assert not app.gate.armed
        app._manual_test()
        assert pump_until(app, lambda: app.gate.waiting_for_paper)
        assert len(sent) == 1
        assert not app.gate.armed

        app._verify_paper()  # mocked acknowledgement
        assert not app.gate.armed  # second explicit arm is still required
        app._arm()
        assert app.gate.will_submit("Canon MF244dw")
        app._start()
        assert pump_until(app, lambda: app.status.get().startswith("監視中"), 4)
        Image.new("RGB", (230, 300), "white").save(inbox / "scan-1.jpg", "JPEG")
        assert pump_until(app, lambda: len(sent) == 2 and
                          any(r["state"] == "SUBMITTED" for r in app.rows_by_id.values()), 9)
        assert sent[1][1] == "Canon MF244dw"
        app._stop()
        assert pump_until(app, lambda: not app.worker.is_alive(), 4)
        assert len(sent) == 2

        # The next process never inherits the simulated approval.
        from m4_print_gate import PrintGate
        assert not PrintGate().will_submit("Canon MF244dw")
    finally:
        app._close()
        try:
            app.update()
        except Exception:
            pass
