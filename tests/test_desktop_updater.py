"""WinSparkle bridge contract tests; no network or executable launch."""
import base64
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from desktop_updater import DesktopUpdater, UpdateReservation, update_allowed

KEY = base64.b64encode(bytes(range(32))).decode()


class FakeFunction:
    def __init__(self, name, calls):
        self.name = name
        self.calls = calls

    def __call__(self, *args):
        self.calls.append((self.name, args))
        if self.name == "win_sparkle_set_eddsa_public_key":
            return 1


class FakeDLL:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        return FakeFunction(name, self.calls)


def test_unprovisioned_build_cannot_update():
    dll = FakeDLL()
    updater = DesktopUpdater(lambda *_: None, library=dll, public_key="", installed=True)
    assert not updater.available
    assert not updater.check(auto_install=True)
    assert not dll.calls


def test_portable_build_cannot_install():
    updater = DesktopUpdater(lambda *_: None, library=FakeDLL(), public_key=KEY, installed=False)
    assert not updater.available


def test_explicit_auto_install_selects_native_api():
    dll = FakeDLL()
    updater = DesktopUpdater(lambda *_: None, library=dll, public_key=KEY, installed=True)
    assert updater.available
    assert updater.check(interactive=False, auto_install=True)
    assert dll.calls[-1][0] == "win_sparkle_check_update_with_ui_and_install"
    assert not updater.check(auto_install=True)
    assert updater.reservation.can_shutdown() == 1
    updater.reservation.finish()
    assert updater.active
    updater.close()
    assert not updater.available
    assert updater.reservation.can_shutdown() == 0


def test_normal_check_does_not_install_automatically():
    dll = FakeDLL()
    updater = DesktopUpdater(lambda *_: None, library=dll, public_key=KEY, installed=True)
    assert updater.check(interactive=False)
    assert dll.calls[-1][0] == "win_sparkle_check_update_without_ui"
    updater.reservation.finish()
    assert not updater.active
    assert updater.reservation.can_shutdown() == 0
    updater.close()


@pytest.mark.parametrize("flag", ["monitoring", "manual", "reprocessing", "waiting", "pending", "armed", "exiting"])
def test_update_blocked_for_every_busy_state(flag):
    state = dict.fromkeys(("monitoring", "manual", "reprocessing", "waiting",
                           "pending", "armed", "exiting"), False)
    assert update_allowed(**state)
    state[flag] = True
    assert not update_allowed(**state)
