"""M4 runtime-only print permission gate.

Never persist permission to disk. No model, mock, user preference or CI result
is evidence of physical paper delivery. A real person must explicitly confirm
one physical trial print from the selected queue in the current process.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class GateError(ValueError):
    """Raised if an unsafe state transition is attempted."""


@dataclass
class PrintGate:
    verified_printer: str | None = None
    verification_preview: Path | None = None
    pending_printer: str | None = None
    pending_preview: Path | None = None
    waiting_for_paper: bool = False
    armed: bool = False
    direct_authorized_printer: str | None = None  # explicit bypass, this process only

    def begin_manual_test(self, printer: str, preview: Path) -> None:
        if self.armed:
            raise GateError("DISARM_BEFORE_MANUAL_TEST")
        if self.pending_printer or self.waiting_for_paper:
            raise GateError("ALREADY_TESTING")
        if not printer or not preview.is_file() or preview.suffix.lower() != ".png":
            raise GateError("INVALID_PRINTER_OR_PREVIEW")
        # Starting any new test revokes the previous verification.
        self.verified_printer = None
        self.verification_preview = None
        self.direct_authorized_printer = None
        self.pending_printer = printer
        self.pending_preview = preview.resolve()

    def manual_submitted(self) -> None:
        if not self.pending_printer or not self.pending_preview or self.waiting_for_paper:
            raise GateError("NO_PENDING_MANUAL_PRINT")
        self.waiting_for_paper = True

    def manual_failed(self) -> None:
        # A submission error may still have produced a printout, but
        # cannot be accepted as proof. Never automatically re-submit.
        self.pending_printer = None
        self.pending_preview = None
        self.waiting_for_paper = False
        self.armed = False
        self.verified_printer = None
        self.verification_preview = None
        self.direct_authorized_printer = None

    def confirm_paper(self, *, paper_present: bool, exactly_one: bool, image_ok: bool) -> None:
        if not self.waiting_for_paper or not self.pending_printer or not self.pending_preview:
            raise GateError("NO_PRINTOUT_TO_VERIFY")
        if paper_present and exactly_one and image_ok:
            self.verified_printer = self.pending_printer
            self.verification_preview = self.pending_preview
        else:
            self.verified_printer = None
            self.verification_preview = None
            self.armed = False
        self.pending_printer = None
        self.pending_preview = None
        self.waiting_for_paper = False

    def set_printer(self, selected: str) -> None:
        if selected != self.verified_printer and selected != self.direct_authorized_printer:
            self.armed = False
        if selected != self.verified_printer:
            self.verified_printer = None
            self.verification_preview = None
        if selected != self.direct_authorized_printer:
            self.direct_authorized_printer = None
        if selected != self.pending_printer:
            # A test in flight cannot authorize a different printer.
            self.pending_printer = None
            self.pending_preview = None
            self.waiting_for_paper = False

    def arm(self, printer: str, explicit_confirmation: bool) -> None:
        if not explicit_confirmation:
            raise GateError("NO_EXPLICIT_PERMISSION")
        if self.waiting_for_paper or self.pending_printer:
            raise GateError("TEST_NOT_VERIFIED")
        if not printer or printer != self.verified_printer or not self.verification_preview:
            raise GateError("PHYSICAL_TRIAL_NOT_VERIFIED_FOR_QUEUE")
        self.armed = True

    def arm_without_trial(self, printer: str, *, explicit_confirmation: bool,
                          acknowledge_unverified: bool) -> None:
        """Opt-in bypass: no paper proof is implied, never persisted."""
        if not printer or not explicit_confirmation or not acknowledge_unverified:
            raise GateError("DIRECT_PRINT_ACKNOWLEDGEMENT_REQUIRED")
        if self.pending_printer or self.waiting_for_paper:
            raise GateError("TEST_NOT_VERIFIED")
        self.verified_printer = None
        self.verification_preview = None
        self.direct_authorized_printer = printer
        self.armed = True

    def disarm(self) -> None:
        self.armed = False
        # Direct consent is single-running-monitor only; stopping requires new consent.
        self.direct_authorized_printer = None

    def reset_for_new_process(self) -> None:
        # Never read persistent on/verified flags from settings.json.
        self.manual_failed()

    def will_submit(self, printer: str) -> bool:
        return bool(self.armed and printer and
                    (printer == self.verified_printer or
                     printer == self.direct_authorized_printer))
