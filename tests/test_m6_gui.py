"""End-to-end Tk test for reprocessing a saved original without rescanning/printing."""
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from m2_monitor import JobStore
from m4_operator_ui import OperatorApp


def test_gui_reprocess_existing_scan_90_degrees_and_disarm(monkeypatch, tmp_path):
    import windows_print
    monkeypatch.setattr(windows_print, "submit_a4",
                        lambda *_a, **_kw: (_ for _ in ()).throw(
                            AssertionError("Never print from reprocess")))
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    source = inbox / "original.jpg"
    image = np.full((540, 420, 3), 43, dtype=np.uint8)
    image[50:500, 50:365] = (233, 230, 218)
    cv2.rectangle(image, (76, 78), (160, 140), (25, 30, 32), -1)
    Image.fromarray(image).save(source)
    output = tmp_path / "results"
    store = JobStore(output / "jobs.sqlite3")
    old = store.claim("ORIGINAL_M6_GUI_TEST", source)
    store.set(old, "READY_REVIEW", "ORIGINAL_NOT_PRINTED")
    store.close()

    app = OperatorApp()
    assert "v0.7.3-rc.1" in app.title()
    app.withdraw()
    try:
        app.inbox.set(str(inbox))
        app.output.set(str(output))
        app._refresh_history()
        app.rotation.set("90")
        app.scale_mode.set("fit")
        app.trim_mm.set("1")
        app.tree.selection_set(old)
        app._reprocess_selected()
        deadline = time.monotonic() + 10
        new_ids = []
        while time.monotonic() < deadline:
            app.update()
            new_ids = [id for id in app.rows_by_id if id != old]
            if new_ids:
                break
            time.sleep(.1)
        assert new_ids, "No new GUI preview job in SQLite history"
        new = app.rows_by_id[new_ids[0]]
        assert new["state"] == "READY_REVIEW"
        app.tree.selection_set(new_ids[0])
        app._update_preview_info()
        assert "回転 90°" in app.preview_info.get()
        assert "A4横" in app.preview_info.get()
        assert "fit" in app.preview_info.get()
        assert "内側カット 1" in app.preview_info.get()
        assert "REPROCESSED_PREVIEW_ONLY" in new["message"]
        with Image.open(new["preview_path"]) as rendered:
            assert rendered.width > rendered.height
        assert app.gate.armed is False
        assert app.rows_by_id[old]["message"] == "ORIGINAL_NOT_PRINTED"
    finally:
        app._close()
        try:
            app.update()
        except Exception:
            pass
