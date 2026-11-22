"""M5: Windows tray companion. All Tk operations stay on the Tk main thread.

No auto-arming, no auto-startup, and no printing from the tray thread.
A missing tray dependency leaves the ordinary window available.
"""
from __future__ import annotations

import os
import threading
from collections.abc import Callable

from PIL import Image, ImageDraw


def make_icon() -> Image.Image:
    """An original monochrome 64px icon; no copyrighted images/fonts."""
    image = Image.new("RGB", (64, 64), "#f7f7f7")
    draw = ImageDraw.Draw(image)
    draw.rectangle((12, 8, 49, 55), outline="#111111", width=4)
    draw.line((18, 20, 42, 20), fill="#111111", width=3)
    draw.line((18, 29, 42, 29), fill="#111111", width=3)
    draw.line((18, 38, 36, 38), fill="#111111", width=3)
    draw.rectangle((17, 45, 28, 48), fill="#111111")
    return image


class TrayController:
    """Windows pystray worker. Menu callbacks only send commands to a queue."""

    def __init__(self, send: Callable[[str], None],
                 *, platform: str | None = None, backend=None):
        self.send = send
        self.platform = platform or os.name
        self.backend = backend  # only for dependency injection in tests
        self.icon = None
        self.thread: threading.Thread | None = None
        self.error: str | None = None

    def start(self) -> bool:
        if self.platform != "nt":
            self.error = "TRAY_WINDOWS_ONLY"
            return False
        if self.icon is not None:
            return True
        try:
            api = self.backend
            if api is None:
                import pystray
                api = pystray
            icon = api.Icon(
                "APP033_BlackCutPrint",
                make_icon(),
                "黒カット印刷",
                menu=api.Menu(
                    api.MenuItem("画面を表示", lambda _icon, _item: self.send("show"), default=True),
                    api.MenuItem("監視を停止", lambda _icon, _item: self.send("stop")),
                    api.MenuItem("終了", lambda _icon, _item: self.send("exit")),
                ),
            )
        except Exception as exc:
            self.error = f"TRAY_INIT_FAILED:{type(exc).__name__}"
            return False

        self.icon = icon
        self.thread = threading.Thread(target=self._run, daemon=True,
                                       name="APP033-tray")
        self.thread.start()
        return True

    def _run(self) -> None:
        try:
            self.icon.run()
        except Exception as exc:
            self.error = f"TRAY_RUN_FAILED:{type(exc).__name__}"
            self.send("tray_error")

    def stop(self) -> None:
        icon = self.icon
        self.icon = None
        if icon is not None:
            try:
                icon.stop()
            except Exception:
                pass
        # The tray worker is daemonized, but do not block Tk shutdown.
