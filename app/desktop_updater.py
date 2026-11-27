"""Optional WinSparkle 0.9.4 integration (MIT), not a custom download/execution engine.

Native callbacks use a thread-safe reservation and a queue; they never call Tk.
Unsigned or unmanaged builds never initialize a downloader.
"""
from __future__ import annotations

import base64
import ctypes
import os
from pathlib import Path
import sys
import threading

from update_identity import PUBLIC_KEY, BUILD_NUMBER, FEED_URL
from version_info import APP_VERSION

VOID_CALLBACK = ctypes.CFUNCTYPE(None)
INT_CALLBACK = ctypes.CFUNCTYPE(ctypes.c_int)
DLL_NAME = "WinSparkle.dll"


def valid_key(key: str) -> bool:
    try:
        return bool(key) and len(base64.b64decode(key, validate=True)) == 32
    except (ValueError, TypeError):
        return False


def managed_install() -> bool:
    if os.name != "nt" or not getattr(sys, "frozen", False):
        return False
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        return False
    root = Path(local) / "Programs" / "BlackCutPrint"
    return Path(sys.executable).resolve().parent == root.resolve()


def update_allowed(*, monitoring: bool, manual: bool, reprocessing: bool,
                   waiting: bool, pending: bool, armed: bool, exiting: bool) -> bool:
    return not any((monitoring, manual, reprocessing, waiting, pending, armed, exiting))


class UpdateReservation:
    """Only explicit idle-session checks can authorize native installer launch."""
    def __init__(self):
        self._lock = threading.Lock()
        self._state = "idle"

    @property
    def active(self) -> bool:
        with self._lock:
            return self._state in ("checking", "installing")

    def begin(self) -> bool:
        with self._lock:
            if self._state != "idle":
                return False
            self._state = "checking"
            return True

    def can_shutdown(self) -> int:
        with self._lock:
            if self._state not in ("checking", "installing"):
                return 0
            self._state = "installing"
            return 1

    def finish(self) -> None:
        with self._lock:
            # Once installation is authorized, do not reopen print controls.
            if self._state == "checking":
                self._state = "idle"

    def close(self) -> None:
        with self._lock:
            self._state = "closed"


class DesktopUpdater:
    def __init__(self, notify, *, library=None, public_key=PUBLIC_KEY,
                 installed=None):
        self.notify = notify
        self.reservation = UpdateReservation()
        self.dll = None
        self.callbacks = []
        self.initialized = False
        self.available = False
        if not valid_key(public_key) or not (managed_install() if installed is None else installed):
            return
        try:
            if library is None:
                if os.name != "nt" or not getattr(sys, "frozen", False):
                    return
                dll_path = Path(sys._MEIPASS).resolve() / DLL_NAME
                if not dll_path.is_file():
                    return
                library = ctypes.CDLL(str(dll_path), winmode=0x1100)
            self.dll = library
            self._configure(public_key)
            self.available = True
        except (OSError, AttributeError, ValueError) as exc:
            self.notify("update_error", f"更新機構を初期化できません: {type(exc).__name__}")

    def _fn(self, name, args=(), result=None):
        fn = getattr(self.dll, "win_sparkle_" + name)
        fn.argtypes = list(args)
        fn.restype = result
        return fn

    def _callback(self, name, prototype, handler):
        callback = prototype(handler)
        self.callbacks.append(callback)  # retain until cleanup
        self._fn(name, (prototype,))(callback)

    def _configure(self, key):
        self._fn("set_appcast_url", (ctypes.c_char_p,))(FEED_URL.encode("ascii"))
        self._fn("set_app_details", (ctypes.c_wchar_p,) * 3)(
            "APP-033", "黒カット印刷", APP_VERSION)
        self._fn("set_app_build_version", (ctypes.c_wchar_p,))(BUILD_NUMBER)
        self._fn("set_lang", (ctypes.c_char_p,))(b"ja")
        if self._fn("set_eddsa_public_key", (ctypes.c_char_p,), ctypes.c_int)(key.encode("ascii")) != 1:
            raise ValueError("INVALID_UPDATE_TRUST_ANCHOR")
        # We own scheduling so no native background check can race active printing.
        self._fn("set_automatic_check_for_updates", (ctypes.c_int,))(0)
        self._callback("set_can_shutdown_callback", INT_CALLBACK, self.reservation.can_shutdown)
        self._callback("set_shutdown_request_callback", VOID_CALLBACK,
                       lambda: self.notify("update_shutdown", None))
        for event in ("did_not_find_update", "update_cancelled", "update_skipped",
                      "update_postponed", "update_dismissed", "error"):
            def terminal(event=event):
                self.reservation.finish()
                self.notify("update_result", event)
            self._callback("set_" + event + "_callback", VOID_CALLBACK, terminal)
        self._callback("set_did_find_update_callback", VOID_CALLBACK,
                       lambda: self.notify("update_found", None))
        self._fn("init")()
        self.initialized = True

    @property
    def active(self):
        return self.reservation.active

    def check(self, *, interactive=True, auto_install=False):
        if not self.available or not self.reservation.begin():
            return False
        try:
            method = ("check_update_with_ui_and_install" if auto_install else
                      "check_update_with_ui" if interactive else "check_update_without_ui")
            self._fn(method)()
            return True
        except Exception:
            self.reservation.finish()
            self.notify("update_result", "error")
            return False

    def close(self):
        self.reservation.close()
        self.available = False
        if self.initialized:
            self.initialized = False
            self._fn("cleanup")()
