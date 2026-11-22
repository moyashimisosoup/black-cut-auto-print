"""APP-033 M2: dedicated scan inbox -> M1 -> guarded Windows print.

Safe defaults: monitoring only, NO printing, ignore every file present at start.
No UI or installer yet. No scanning-device control. The Windows GDI adapter is
not yet verified with physical Canon MF244dw hardware.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import sqlite3
import threading
import time
import uuid
from typing import Callable

from m1_processing import process

EXTENSIONS = {".jpg", ".jpeg"}  # MF Scan Utility JPEG only in M2
MAX_SOURCE_BYTES = 100 * 1024 * 1024


class JobStore:
    """Durable idempotence: one stable source identity may be claimed once."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, timeout=30)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=FULL")
        self.connection.execute("""CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            fingerprint TEXT UNIQUE NOT NULL,
            source_path TEXT NOT NULL,
            state TEXT NOT NULL,
            message TEXT NOT NULL DEFAULT '',
            preview_path TEXT NOT NULL DEFAULT '',
            spool_id TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        # Interrupted print submission is ambiguous, so NEVER resend.
        self.connection.execute("""
            UPDATE jobs SET state='UNKNOWN',
                message='PRINT_INTERRUPTED_NO_AUTO_RETRY',
                updated_at=CURRENT_TIMESTAMP
            WHERE state='SUBMITTING'
        """)
        self.connection.execute("""
            UPDATE jobs SET state='HOLD',
                message='PROCESSING_INTERRUPTED_NO_AUTO_RETRY',
                updated_at=CURRENT_TIMESTAMP
            WHERE state IN ('NEW', 'PROCESSING')
        """)
        self.connection.commit()

    def claim(self, fingerprint: str, source_path: Path) -> str | None:
        job = uuid.uuid4().hex
        c = self.connection.execute(
            "INSERT OR IGNORE INTO jobs(id, fingerprint, source_path, state) "
            "VALUES (?, ?, ?, 'NEW')",
            (job, fingerprint, str(source_path)),
        )
        self.connection.commit()
        return job if c.rowcount == 1 else None

    def set(self, job_id: str, state: str, message: str = "",
            preview_path: str = "", spool_id: int | None = None) -> None:
        self.connection.execute(
            "UPDATE jobs SET state=?, message=?, preview_path=?, spool_id=?, "
            "updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (state, message[:280], preview_path, str(spool_id) if spool_id is not None else None, job_id),
        )
        self.connection.commit()

    def rows(self) -> list[dict]:
        self.connection.row_factory = sqlite3.Row
        return [dict(row) for row in self.connection.execute(
            "SELECT * FROM jobs ORDER BY rowid"
        ).fetchall()]

    def close(self) -> None:
        self.connection.close()


class SingleInstance:
    """OS advisory file lock prevents two monitor processes sharing state."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = open(path, "a+b")
        try:
            self.handle.seek(0, os.SEEK_END)
            if self.handle.tell() == 0:
                self.handle.write(b"0")
                self.handle.flush()
            self.handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.handle.close()
            raise RuntimeError("MONITOR_ALREADY_RUNNING") from exc

    def close(self) -> None:
        if self.handle.closed:
            return
        self.handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close()


def source_fingerprint(path: Path) -> str:
    st = path.stat()
    payload = f"{path.resolve()}\0{st.st_size}\0{st.st_mtime_ns}\0{st.st_ctime_ns}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ScanPipeline:
    def __init__(self, store: JobStore, output: Path, *,
                 printer: str | None = None, armed: bool = False,
                 sender: Callable[[Path, str], int | None] | None = None,
                 source_dpi: float | None = None, rotate: int = 0,
                 scale_mode: str = "nominal", trim_mm: float = 0,
                 stop: threading.Event | None = None):
        self.store = store
        self.output = output
        self.printer = printer
        self.armed = armed
        self.sender = sender
        self.source_dpi = source_dpi
        if scale_mode not in {"nominal", "fit"}:
            raise ValueError("INVALID_SCALE_MODE")
        self.rotate = rotate
        if trim_mm not in (0, 1, 2, 3, 5):
            raise ValueError("INVALID_TRIM_SETTINGS")
        self.scale_mode = scale_mode
        self.trim_mm = trim_mm
        self.stop = stop or threading.Event()

    def hold_unstable(self, source: Path) -> None:
        """Persist timeout as HOLD instead of silently dropping the file."""
        try:
            fingerprint = source_fingerprint(source)
            job = self.store.claim(fingerprint, source)
            if job:
                self.store.set(job, "HOLD", "STABILIZATION_TIMEOUT")
        except OSError:
            pass

    def run_one(self, source: Path) -> str:
        if source.is_symlink() or source.suffix.lower() not in EXTENSIONS:
            return "IGNORED"
        if not source.is_file() or not 0 < source.stat().st_size <= MAX_SOURCE_BYTES:
            return "IGNORED"
        fingerprint = source_fingerprint(source)
        job_id = self.store.claim(fingerprint, source)
        if job_id is None:
            return "DUPLICATE"
        out = self.output / "jobs" / job_id
        self.store.set(job_id, "PROCESSING")
        try:
            result = process(source, out, rotation=self.rotate, output_dpi=300,
                             source_dpi=self.source_dpi, scale_mode=self.scale_mode,
                             trim_mm=self.trim_mm)
        except Exception as exc:
            self.store.set(job_id, "HOLD", f"PROCESSING_ERROR:{type(exc).__name__}")
            return "HOLD"
        if result.status != "ACCEPT":
            self.store.set(job_id, "HOLD", result.reason)
            return "HOLD"
        preview = out / "a4_preview.png"
        if not preview.is_file():
            self.store.set(job_id, "HOLD", "PREVIEW_NOT_WRITTEN")
            return "HOLD"
        if self.stop.is_set():
            self.store.set(job_id, "HOLD", "MONITOR_STOPPED_BEFORE_SUBMISSION", str(preview))
            return "HOLD"
        if not self.armed:
            self.store.set(job_id, "READY_REVIEW", "DRY_RUN_NO_PRINT", str(preview))
            return "READY_REVIEW"
        if not self.printer or self.sender is None:
            self.store.set(job_id, "HOLD", "PRINTER_NOT_CONFIGURED", str(preview))
            return "HOLD"
        # DB commit MUST precede the first print API call.
        self.store.set(job_id, "SUBMITTING", "SPOOLER_RESULT_NOT_YET_KNOWN", str(preview))
        try:
            spool_id = self.sender(preview, self.printer)
        except BaseException as exc:
            # Even an API error may mean the spooler accepted an earlier part.
            self.store.set(job_id, "UNKNOWN", f"PRINT_SUBMISSION_UNKNOWN:{type(exc).__name__}", str(preview))
            return "UNKNOWN"
        self.store.set(job_id, "SUBMITTED", "SPOOLER_ACCEPTED_NOT_PAPER_VERIFIED",
                       str(preview), spool_id)
        return "SUBMITTED"


class InboxMonitor:
    """Nonrecursive polling; low-idle-overhead and no driver-specific hooks."""

    def __init__(self, inbox: Path, pipeline: ScanPipeline, *,
                 settle_seconds: float = 2.5, timeout_seconds: float = 120):
        self.inbox = inbox
        self.pipeline = pipeline
        self.settle_seconds = settle_seconds
        self.timeout_seconds = timeout_seconds
        # Important: never print existing files when the program starts.
        self.known_names = {p.name.casefold() for p in inbox.iterdir() if p.is_file()}
        self.pending: dict[str, tuple[tuple[int, int], float, float]] = {}

    def poll_once(self, now: float | None = None) -> list[tuple[str, str]]:
        now = time.monotonic() if now is None else now
        outcomes: list[tuple[str, str]] = []
        try:
            entries = list(self.inbox.iterdir())
        except OSError:
            raise RuntimeError("INBOX_UNAVAILABLE")
        present: set[str] = set()
        for entry in entries:
            key = entry.name.casefold()
            present.add(key)
            if key in self.known_names or entry.suffix.lower() not in EXTENSIONS:
                continue
            if entry.is_symlink() or not entry.is_file():
                self.known_names.add(key)
                continue
            try:
                st = entry.stat()
            except OSError:
                continue
            signature = (st.st_size, st.st_mtime_ns)
            if key not in self.pending:
                self.pending[key] = (signature, now, now)
                continue
            last_sig, stable_since, first_seen = self.pending[key]
            if signature != last_sig:
                self.pending[key] = (signature, now, first_seen)
                continue
            if now - first_seen > self.timeout_seconds:
                self.known_names.add(key)
                self.pending.pop(key, None)
                self.pipeline.hold_unstable(entry)
                outcomes.append((entry.name, "STABILIZATION_TIMEOUT_HOLD"))
                continue
            if st.st_size > MAX_SOURCE_BYTES:
                self.known_names.add(key)
                self.pending.pop(key, None)
                self.pipeline.hold_unstable(entry)
                outcomes.append((entry.name, "SOURCE_TOO_LARGE_HOLD"))
                continue
            if st.st_size == 0 or now - stable_since < self.settle_seconds:
                continue
            # Do not inspect a partially written JPEG. PIL.verify performs
            # structure checks; M1 will also fully decode before printing.
            try:
                from PIL import Image
                with Image.open(entry) as im:
                    im.verify()
            except (OSError, ValueError, SyntaxError):
                continue
            self.known_names.add(key)
            self.pending.pop(key, None)
            outcome = self.pipeline.run_one(entry)
            outcomes.append((entry.name, outcome))
        # Deleted or renamed temp files must not remain pending.
        for missing in set(self.pending) - present:
            self.pending.pop(missing, None)
        return outcomes


def _paths_safe(inbox: Path, output: Path) -> bool:
    """Prevent the nonrecursive inbox from receiving our generated files.

    A sibling output or parent of the inbox (even a drive root) is safe:
    InboxMonitor only reads direct children of the designated inbox.
    Output *inside* the inbox is not safe: the monitor could see outputs
    and future formats as incoming scans.
    """
    inbox = inbox.resolve()
    output = output.resolve()
    return output != inbox and inbox not in output.parents


def run_cli(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="APP-033 M2. Monitor is OFF unless this command runs; printing is OFF by default.")
    p.add_argument("--inbox", type=Path, help="Existing dedicated Canon JPEG scan folder")
    p.add_argument("--output", type=Path, help="Local results folder (outside inbox)")
    p.add_argument("--printer", help="EXACT Windows printer queue name; no default fallback")
    p.add_argument("--arm-printing", action="store_true", help="Enable unattended printer submission (unsafe before validation)")
    p.add_argument("--confirm-reviewed", action="store_true", help="I reviewed M1 previews and completed a manual hardware test")
    p.add_argument("--list-printers", action="store_true")
    p.add_argument("--manual-test-print", type=Path, help="Send existing A4 preview once. Does not monitor.")
    p.add_argument("--confirm-test-sheet", action="store_true", help="I understand this command sends ONE physical print job")
    p.add_argument("--rotate", type=int, choices=(0, 90, 180, 270), default=0)
    p.add_argument("--source-dpi", type=float)
    p.add_argument("--scale-mode", choices=("nominal", "fit"), default="nominal")
    p.add_argument("--trim-mm", type=float, choices=(0, 1, 2, 3, 5), default=0)
    p.add_argument("--poll-seconds", type=float, default=0.75)
    p.add_argument("--settle-seconds", type=float, default=2.5)
    args = p.parse_args(argv)

    if args.list_printers:
        from windows_print import list_printers
        for item in list_printers():
            print(item)
        return 0
    if args.arm_printing and not args.confirm_reviewed:
        p.error("--arm-printing requires --confirm-reviewed (manual test and M1 review first)")
    if args.manual_test_print:
        if args.arm_printing or not args.confirm_test_sheet or not args.printer:
            p.error("--manual-test-print requires --printer and --confirm-test-sheet; do not combine --arm-printing")
        from windows_print import submit_a4
        print(json.dumps({"spool_id": submit_a4(args.manual_test_print, args.printer),
                          "status": "SUBMITTED_NOT_PAPER_VERIFIED"}))
        return 0
    if not args.inbox or not args.output:
        p.error("--inbox and --output are required")
    if args.arm_printing and (not args.printer or os.name != "nt"):
        p.error("armed printing requires Windows and --printer EXACT queue name")
    if args.arm_printing:
        from windows_print import list_printers
        if args.printer not in list_printers():
            p.error("named printer not found in Windows printer queue list")
    if not 0.25 <= args.poll_seconds <= 10 or not 1 <= args.settle_seconds <= 30:
        p.error("invalid poll/settle settings")
    if args.source_dpi is not None and not 72 <= args.source_dpi <= 1200:
        p.error("source DPI must be 72..1200")
    inbox, output = args.inbox.resolve(), args.output.resolve()
    if not inbox.is_dir() or not _paths_safe(inbox, output):
        p.error("inbox must exist; output cannot equal or be inside inbox")
    output.mkdir(parents=True, exist_ok=True)
    stop = threading.Event()

    def _stop(_signum, _frame):
        stop.set()

    signal.signal(signal.SIGINT, _stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _stop)
    from windows_print import submit_a4
    instance_lock = SingleInstance(output / ".monitor.lock")
    try:
        store = JobStore(output / "jobs.sqlite3")
    except BaseException:
        instance_lock.close()
        raise
    try:
        sender = submit_a4 if args.arm_printing else None
        pipeline = ScanPipeline(store, output, printer=args.printer,
                                armed=args.arm_printing, sender=sender,
                                source_dpi=args.source_dpi, rotate=args.rotate,
                                scale_mode=args.scale_mode, trim_mm=args.trim_mm, stop=stop)
        monitor = InboxMonitor(inbox, pipeline, settle_seconds=args.settle_seconds)
        print(f"MONITOR_ON printing={'ARMED' if args.arm_printing else 'DISABLED'}; old files ignored; Ctrl+C to stop", flush=True)
        while not stop.is_set():
            for name, status in monitor.poll_once():
                print(json.dumps({"file": name, "status": status}, ensure_ascii=False), flush=True)
            stop.wait(args.poll_seconds)
        print("MONITOR_OFF", flush=True)
        return 0
    finally:
        store.close()
        instance_lock.close()


if __name__ == "__main__":
    raise SystemExit(run_cli())
