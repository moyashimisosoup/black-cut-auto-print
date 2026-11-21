"""M5 tray tests: all backend and icon callbacks are mocked."""
from __future__ import annotations

import threading
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from m5_tray import TrayController, make_icon


def test_icon_is_original_self_contained_bitmap():
    image = make_icon()
    assert image.size == (64, 64)
    assert image.mode == "RGB"
    assert image.getpixel((0, 0)) != image.getpixel((12, 12))


def test_non_windows_tray_is_optional_and_does_not_touch_system():
    commands = []
    tray = TrayController(commands.append, platform="posix")
    assert not tray.start()
    assert tray.error == "TRAY_WINDOWS_ONLY"
    assert tray.icon is None
    tray.stop()


class FakeIcon:
    def __init__(self, name, image, title, menu):
        self.name = name
        self.image = image
        self.title = title
        self.menu = menu
        self.ready = threading.Event()
        self.stopping = threading.Event()

    def run(self):
        self.ready.set()
        assert self.stopping.wait(timeout=4), "tray stop() must end the worker"

    def stop(self):
        self.stopping.set()


class FakeBackend:
    Icon = FakeIcon

    @staticmethod
    def Menu(*items):
        return items

    @staticmethod
    def MenuItem(label, callback, **kwargs):
        return SimpleNamespace(text=label, action=callback, opts=kwargs)


def test_menu_callbacks_only_forward_user_actions():
    called = []
    tray = TrayController(called.append, platform="nt", backend=FakeBackend())
    assert tray.start()
    assert tray.icon.ready.wait(timeout=2)
    assert [x.text for x in tray.icon.menu] == ["画面を表示", "監視を停止", "終了"]
    for item in tray.icon.menu:
        item.action(None, None)
    assert called == ["show", "stop", "exit"]
    assert tray.start()  # double-start is idempotent
    worker = tray.thread
    tray.stop()
    worker.join(timeout=3)
    assert not worker.is_alive()
    assert tray.icon is None


def test_backend_failure_does_not_crash_main_window():
    class Broken:
        @staticmethod
        def Icon(*args, **kwargs):
            raise RuntimeError("tray unavailable")
        Menu = FakeBackend.Menu
        MenuItem = FakeBackend.MenuItem

    tray = TrayController(lambda value: None, platform="nt", backend=Broken())
    assert not tray.start()
    assert tray.error == "TRAY_INIT_FAILED:RuntimeError"
    tray.stop()
