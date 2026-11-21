"""Windows GDI print adapter for APP-033.

NEVER import this module to print implicitly. No default-printer fallback.
This adapter is unverified on Canon MF244dw hardware. Always test manually
before arming unattended scans.
"""
from __future__ import annotations

import os
from pathlib import Path


class PrinterError(RuntimeError):
    pass


def list_printers() -> list[str]:
    if os.name != "nt":
        raise PrinterError("WINDOWS_ONLY")
    import win32print  # type: ignore[import-not-found]

    flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
    return sorted({row[2] for row in win32print.EnumPrinters(flags)})


def _check_a4(w: int, h: int) -> bool:
    if min(w, h) < 500:
        return False
    ratio = max(w, h) / min(w, h)
    return abs(ratio - (297 / 210)) < 0.035


def _physical_a4(pw: int, ph: int, dpi_x: int, dpi_y: int) -> bool:
    """Reject larger paper sizes (e.g., A3) even though aspect ratios match."""
    if min(pw, ph, dpi_x, dpi_y) <= 0:
        return False
    physical_mm = (pw * 25.4 / dpi_x, ph * 25.4 / dpi_y)
    expected = (297, 210) if pw > ph else (210, 297)
    return all(abs(actual - target) < 7 for actual, target in zip(physical_mm, expected))


def submit_a4(image_path: Path, printer_name: str) -> int | None:
    """Send exactly one one-sided monochrome A4 document to named queue.

    Return StartDoc spooler job ID if available. Return != physical delivery.
    Any exception, including one after StartDoc, must be treated as UNKNOWN
    by caller; never automatically retry.
    """
    if os.name != "nt":
        raise PrinterError("WINDOWS_ONLY")
    if not printer_name or printer_name not in list_printers():
        raise PrinterError("PRINTER_NOT_FOUND_EXACT")
    from PIL import Image, ImageWin
    import win32con  # type: ignore[import-not-found]
    import win32gui  # type: ignore[import-not-found]
    import win32print  # type: ignore[import-not-found]

    with Image.open(image_path) as opened:
        opened.load()
        if not _check_a4(*opened.size):
            raise PrinterError("NOT_A4_PREVIEW")
        image = opened.convert("RGB").copy()
    landscape = image.width > image.height

    printer_handle = win32print.OpenPrinter(printer_name)
    try:
        details = win32print.GetPrinter(printer_handle, 2)
        dm = details.get("pDevMode")
        status = int(details.get("Status") or 0)
        unsafe = (win32print.PRINTER_STATUS_OFFLINE |
                  win32print.PRINTER_STATUS_PAUSED |
                  win32print.PRINTER_STATUS_ERROR |
                  win32print.PRINTER_STATUS_PAPER_OUT)
        if status & unsafe:
            raise PrinterError("PRINTER_NOT_READY_OR_OFFLINE")
        if dm is None:
            raise PrinterError("DRIVER_DEVMODE_UNAVAILABLE")
        dm.Fields |= (win32con.DM_PAPERSIZE | win32con.DM_ORIENTATION |
                      win32con.DM_COPIES | win32con.DM_DUPLEX |
                      win32con.DM_COLOR)
        dm.PaperSize = win32con.DMPAPER_A4
        dm.Orientation = (win32con.DMORIENT_LANDSCAPE if landscape
                          else win32con.DMORIENT_PORTRAIT)
        dm.Copies = 1
        dm.Duplex = win32con.DMDUP_SIMPLEX
        dm.Color = win32con.DMCOLOR_MONOCHROME

        # Create a document-specific device context; DO NOT change Windows
        # system defaults or queue-wide printer settings.
        hdc = win32gui.CreateDC("WINSPOOL", printer_name, None, dm)
        started = False
        try:
            pw = win32print.GetDeviceCaps(hdc, win32con.PHYSICALWIDTH)
            ph = win32print.GetDeviceCaps(hdc, win32con.PHYSICALHEIGHT)
            ox = win32print.GetDeviceCaps(hdc, win32con.PHYSICALOFFSETX)
            oy = win32print.GetDeviceCaps(hdc, win32con.PHYSICALOFFSETY)
            printable_w = win32print.GetDeviceCaps(hdc, win32con.HORZRES)
            printable_h = win32print.GetDeviceCaps(hdc, win32con.VERTRES)
            dpi_x = win32print.GetDeviceCaps(hdc, win32con.LOGPIXELSX)
            dpi_y = win32print.GetDeviceCaps(hdc, win32con.LOGPIXELSY)
            if min(pw, ph, printable_w, printable_h) <= 0:
                raise PrinterError("INVALID_DEVICE_CAPABILITIES")
            if not _check_a4(pw, ph) or (pw > ph) != landscape or not _physical_a4(pw, ph, dpi_x, dpi_y):
                raise PrinterError("DRIVER_DID_NOT_SELECT_A4_OR_ORIENTATION")
            if not (0 <= ox < pw and 0 <= oy < ph):
                raise PrinterError("INVALID_PRINT_OFFSETS")
            # Draw full A4 image in physical-page coordinates; the driver
            # clips the unprintable border. M1 preview already has >=5mm white.
            rect = (-ox, -oy, pw - ox, ph - oy)
            dib = ImageWin.Dib(image)
            job_id = win32print.StartDoc(hdc, ("APP-033 Black Cut Print", None, None, 0))
            started = True
            win32print.StartPage(hdc)
            dib.draw(hdc, rect)
            win32print.EndPage(hdc)
            win32print.EndDoc(hdc)
            started = False
            return int(job_id) if job_id else None
        except BaseException:
            if started:
                try:
                    win32print.AbortDoc(hdc)
                except Exception:
                    pass
            raise
        finally:
            win32gui.DeleteDC(hdc)
    finally:
        win32print.ClosePrinter(printer_handle)
