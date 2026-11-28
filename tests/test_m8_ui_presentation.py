"""UI presentation and stop-before-reprocess contract, no real printer."""
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from m4_operator_ui import OperatorApp, format_jst


@pytest.mark.parametrize(("value", "expected"), [
    ("2026-11-28 18:10:00", "2026/11/29 03:10:00"),
    ("2026-12-31T23:59:59Z", "2027/01/01 08:59:59"),
    ("2026-11-29T10:00:00+09:00", "2026/11/29 10:00:00"),
    ("unknown", "unknown"),
    (None, ""),
])
def test_history_jst(value, expected):
    assert format_jst(value) == expected


def test_reprocess_waits_until_monitor_thread_finishes():
    app = SimpleNamespace(pending_exit=False, reprocess_after_stop="job1",
                          worker=Mock(), after=Mock(),
                          _finish_reprocess_stop=Mock(), _refresh_history=Mock())
    app.worker.is_alive.return_value = True
    OperatorApp._finish_reprocess_stop(app)
    app.after.assert_called_once_with(100, app._finish_reprocess_stop)
    app._refresh_history.assert_not_called()
    assert app.reprocess_after_stop == "job1"


def test_armed_monitor_cannot_reprocess():
    app = SimpleNamespace(pending_exit=False, reprocess_after_stop=None,
                          worker=Mock(), monitor_armed=True, _update_active=lambda: False,
                          _selected_row=lambda: {"id": "job1"}, _stop=Mock())
    app.worker.is_alive.return_value = True
    OperatorApp._reprocess_selected(app)
    app._stop.assert_not_called()


def test_exit_cancels_deferred_reprocessing():
    app = SimpleNamespace(pending_exit=True, reprocess_after_stop="job1",
                          _refresh_history=Mock())
    OperatorApp._finish_reprocess_stop(app)
    assert app.reprocess_after_stop is None
    app._refresh_history.assert_not_called()
