"""Guarded, recoverable cleanup of newly scanned JPEGs after queue 'PRINTED'.

SUBMITTED/EndDoc success, a disappearing spooler job, and printer-online state
are NOT proof of output. Never delete in any of those states.
"""
from __future__ import annotations

import os
from pathlib import Path


def spooler_print_status(printer_name: str, job_id: int) -> str:
    """PRINTED only on an explicit Windows JOB_STATUS_PRINTED flag.

    The driver may remove completed jobs without exposing that flag. Treat
    inaccessible/disappeared/error jobs as UNKNOWN and retain the JPEG.
    """
    if os.name != "nt" or not printer_name or not job_id or job_id <= 0:
        return "UNKNOWN"
    try:
        import win32print  # type: ignore[import-not-found]

        handle = win32print.OpenPrinter(printer_name)
        try:
            job = win32print.GetJob(handle, int(job_id), 1)
            flags = int(job.get("Status") or 0)
            if flags & int(win32print.JOB_STATUS_PRINTED):
                return "PRINTED"
            unsafe = (win32print.JOB_STATUS_ERROR | win32print.JOB_STATUS_DELETING |
                      win32print.JOB_STATUS_OFFLINE | win32print.JOB_STATUS_PAPEROUT |
                      win32print.JOB_STATUS_BLOCKED_DEVQ)
            if flags & unsafe:
                return "UNKNOWN"
            return "PENDING"
        finally:
            win32print.ClosePrinter(handle)
    except Exception:
        return "UNKNOWN"


def recycle_scanned_source(source: Path, inbox: Path, expected_fingerprint: str,
                           *, trash=None) -> str:
    """Move only the unchanged, direct inbox JPEG to the Windows recycle bin.

    No hard-delete, no path symlinks, no arbitrary history/manual files, no
    replacement of a filename by a subsequent scan. Fails closed.
    """
    from m2_monitor import EXTENSIONS, source_fingerprint

    try:
        inbox = inbox.resolve(strict=True)
        # Preserve original Path for symlink detection before resolve.
        if (source.is_symlink() or source.suffix.lower() not in EXTENSIONS or
                not source.is_file() or source.parent.resolve(strict=True) != inbox):
            return "SOURCE_UNSAFE_RETAINED"
        if source_fingerprint(source) != expected_fingerprint:
            return "SOURCE_CHANGED_RETAINED"
        # No deletion fallback if recycling is unavailable or denied.
        if trash is None:
            from send2trash import send2trash as trash
        trash(str(source))
        return "SOURCE_RECYCLED"
    except Exception:
        return "SOURCE_RECYCLE_FAILED_RETAINED"
