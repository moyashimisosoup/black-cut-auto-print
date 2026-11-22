"""APP-033 M6: manually remake an existing scan preview without printing.

This intentionally does NOT call Windows printing APIs. Old jobs stay intact.
The one-process lock prevents a concurrent scan monitor from writing the DB.
"""
from __future__ import annotations

from pathlib import Path
import uuid

from m1_processing import process
from m2_monitor import EXTENSIONS, MAX_SOURCE_BYTES, JobStore, SingleInstance


def reprocess_preview(source: Path, output: Path, *,
                      rotation: int, source_dpi: float,
                      scale_mode: str = "nominal", trim_mm: float = 0) -> tuple[str, str]:
    """Return (state, new_job_id); accepts older JPEGs only by explicit action."""
    if rotation not in (0, 90, 180, 270) or not 72 <= source_dpi <= 1200:
        raise ValueError("INVALID_PREVIEW_SETTINGS")
    if scale_mode not in {"nominal", "fit"}:
        raise ValueError("INVALID_SCALE_MODE")
    if trim_mm not in (0, 1, 2, 3, 5):
        raise ValueError("INVALID_TRIM_SETTINGS")
    if (source.is_symlink() or source.suffix.lower() not in EXTENSIONS or
            not source.is_file() or not 0 < source.stat().st_size <= MAX_SOURCE_BYTES):
        raise ValueError("SOURCE_NOT_AVAILABLE")
    output = output.resolve()
    if not output.is_dir():
        raise ValueError("OUTPUT_NOT_AVAILABLE")
    lock = SingleInstance(output / ".monitor.lock")
    try:
        store = JobStore(output / "jobs.sqlite3")
        try:
            # New identity is deliberate: retries/rotations get separate previews,
            # while the source JPEG and every previous job remain untouched.
            job_id = store.claim("MANUAL_PREVIEW:" + uuid.uuid4().hex, source.resolve())
            if job_id is None:
                raise RuntimeError("JOB_ID_COLLISION")
            store.set(job_id, "PROCESSING", "PREVIEW_ONLY_NO_PRINT")
            target = output / "jobs" / job_id
            try:
                report = process(source, target, rotation=rotation, output_dpi=300,
                                 source_dpi=source_dpi, scale_mode=scale_mode,
                                 trim_mm=trim_mm)
                preview = target / "a4_preview.png"
                if report.status != "ACCEPT" or not preview.is_file():
                    store.set(job_id, "HOLD", "PREVIEW_REPROCESS_HOLD:" + report.reason)
                    return "HOLD", job_id
            except Exception as exc:
                store.set(job_id, "HOLD", "PREVIEW_REPROCESS_ERROR:" + type(exc).__name__)
                return "HOLD", job_id
            store.set(job_id, "READY_REVIEW",
                      f"REPROCESSED_PREVIEW_ONLY:rotate={rotation}:scale={scale_mode}:trim={trim_mm}mm",
                      str(preview))
            return "READY_REVIEW", job_id
        finally:
            store.close()
    finally:
        lock.close()
