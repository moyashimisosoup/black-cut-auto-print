"""Validate that an A4 preview used for paper proof matches unattended settings.

Do not infer validation from the user-selected filename alone. A prior image may
have been produced with a different rotation, DPI, scale or crop depth.
"""
from __future__ import annotations

import json
import math
from pathlib import Path


class PreviewMismatch(ValueError):
    pass


def check_preview_for_print(preview: Path, *, rotation: int, dpi: float,
                            scale_mode: str, trim_mm: float) -> None:
    """Fail closed for missing metadata, HOLD results, or skipped trim."""
    if not preview.is_file() or preview.name != "a4_preview.png":
        raise PreviewMismatch("A4プレビューがありません。")
    metadata = preview.parent / "report.json"
    try:
        report = json.loads(metadata.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        raise PreviewMismatch("旧版の画像には設定情報がありません。現在の設定で再加工してください。") from exc
    if not isinstance(report, dict) or report.get("status") != "ACCEPT":
        raise PreviewMismatch("この原稿は正常処理済みではありません。")
    if (report.get("rotation_degrees") != rotation or
            report.get("scale_mode") != scale_mode or
            report.get("a4_orientation") not in {"portrait", "landscape"}):
        raise PreviewMismatch("試し刷りする画像の回転・A4配置が現在の設定と異なります。再加工してください。")
    try:
        source_dpi = float(report.get("source_dpi"))
        applied_trim = float(report.get("trim_mm", 0))
    except (TypeError, ValueError) as exc:
        raise PreviewMismatch("読み取りDPI・内側カットの記録がありません。再加工してください。") from exc
    if (not math.isfinite(source_dpi) or not math.isfinite(applied_trim) or
            abs(source_dpi - dpi) > 0.01 or abs(applied_trim - trim_mm) > 0.01):
        raise PreviewMismatch("試し刷り画像と現在の読取DPI・内側カット量が異なります。再加工してください。")
    if trim_mm and (report.get("trim_warning") == "TRIM_SKIPPED_NO_PAPER_BOUNDARY" or
                    not report.get("trim_pixels")):
        raise PreviewMismatch("追加カットが適用されなかった画像です。内側カット0mmに戻すか別の原稿で試してください。")
