"""Xvfb test: Tk tray queue controls are executed on Tk thread only."""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import m4_operator_ui


class FakeTray:
    instances = []

    def __init__(self, send):
        self.send = send
        self.error = None
        self.started = False
        self.stopped = False
        self.instances.append(self)

    def start(self):
        self.started = True
        return True

    def stop(self):
        self.stopped = True


def test_gui_tray_restore_stop_and_exit(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(m4_operator_ui, "TrayController", FakeTray)
    app = m4_operator_ui.OperatorApp()
    fake = FakeTray.instances[-1]
    try:
        assert fake.started and not fake.stopped
        assert app.gate.armed is False
        # Queue events: never directly manipulate Tk from the tray worker.
        app.withdraw()
        fake.send("show")
        app._events()
        assert app.state() == "normal"

        preview = tmp_path / "preview.png"
        preview.write_bytes(b"synthetic placeholder, never printed")
        app.gate.begin_manual_test("Canon MF244dw", preview)
        app.gate.manual_submitted()
        app.gate.confirm_paper(paper_present=True, exactly_one=True, image_ok=True)
        app.gate.arm("Canon MF244dw", explicit_confirmation=True)
        assert app.gate.armed
        # Even an inactive monitor must disarm from tray STOP.
        fake.send("stop")
        app._events()
        assert not app.gate.armed

        fake.send("exit")
        app._events()
        assert fake.stopped
    finally:
        if not fake.stopped:
            app._close()


def test_explicit_stop_disarms_even_without_tray(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(m4_operator_ui, "TrayController", FakeTray)
    app = m4_operator_ui.OperatorApp()
    try:
        preview = tmp_path / "preview.png"
        preview.write_bytes(b"synthetic placeholder")
        app.gate.begin_manual_test("Canon MF244dw", preview)
        app.gate.manual_submitted()
        app.gate.confirm_paper(paper_present=True, exactly_one=True, image_ok=True)
        app.gate.arm("Canon MF244dw", explicit_confirmation=True)
        app._stop()
        assert app.stop_event.is_set()
        assert not app.gate.armed
    finally:
        app._close()
