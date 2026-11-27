"""Version labels are intentionally stable within a packaged evaluation build."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from version_info import APP_ID, APP_VERSION, version_label, window_title


def test_version_title_has_release_identifier():
    assert APP_ID == "APP-033"
    assert APP_VERSION == "0.7.3-rc.1"
    assert version_label() == "v0.7.3-rc.1"
    assert window_title() == "黒カット印刷 v0.7.3-rc.1 | APP-033"
