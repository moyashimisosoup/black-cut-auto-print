"""Fully simulated physical acknowledgement -> armed scan -> mocked spooler.

THIS TEST NEVER SENDS ANY PRINT JOB. It only tests UI wiring and state gates.
"""
import json
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
    (image.parent / "report.json").write_text(json.dumps({
        "status": "ACCEPT", "rotation_degrees": 0,
        "scale_mode": "nominal", "a4_orientation": "portrait",
        "source_dpi": 300.0, "trim_mm": 0
    }), encoding="utf-8")

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
        app._sync_gate_controls()
        # The four approval buttons must read left-to-right, without jumping
        # between different parts of the window to find the next action.
        steps = [app.manual_button, app.verify_button, app.arm_button, app.start_button]
        assert [button.grid_info()["column"] for button in steps] == [0, 1, 2, 3]
        assert all(button.master == steps[0].master for button in steps)
        assert [button.cget("text") for button in steps[:3]] == [
            "① 1枚試し刷り", "② 紙の結果を確認", "③ 自動印刷を許可"
        ]
        assert "監視のみ開始（印刷OFF）" == app.start_button.cget("text")
        assert "①" in app.workflow_hint.get()
        assert app.verify_button.instate(["disabled"])
        assert app.arm_button.instate(["!disabled"])  # user can deliberately bypass trial
        # Initial state must never submit just because a preview exists.
        assert not app.gate.armed
        app._manual_test()
        assert pump_until(app, lambda: app.gate.waiting_for_paper)
        assert len(sent) == 1
        assert app.verify_button.instate(["!disabled"])
        assert app.arm_button.instate(["disabled"])
        assert "次は②" in app.workflow_hint.get()
        assert not app.gate.armed

        app._verify_paper()  # mocked acknowledgement
        assert not app.gate.armed  # second explicit arm is still required
        assert app.arm_button.instate(["!disabled"])
        assert app.start_button.cget("text") == "監視のみ開始（印刷OFF）"
        assert "次は③" in app.workflow_hint.get()
        app._arm()
        assert app.gate.will_submit("Canon MF244dw")
        assert app.start_button.cget("text") == "④ 監視開始（自動印刷）"
        assert "次は④" in app.workflow_hint.get()
        app._start()
        assert pump_until(app, lambda: app.status.get().startswith("監視中"), 4)
        assert app.manual_button.instate(["disabled"])
        assert app.arm_button.instate(["disabled"])
        assert app.stop_button.instate(["!disabled"])
        assert "自動印刷の監視中" in app.workflow_hint.get()
        Image.new("RGB", (230, 300), "white").save(inbox / "scan-1.jpg", "JPEG")
        assert pump_until(app, lambda: len(sent) == 2 and
                          any(r["state"] == "SUBMITTED" for r in app.rows_by_id.values()), 9)
        assert sent[1][1] == "Canon MF244dw"
        app._stop()
        assert pump_until(app, lambda: not app.worker.is_alive(), 4)
        app._sync_gate_controls()
        assert app.start_button.cget("text") == "監視のみ開始（印刷OFF）"
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
