"""No hardware, no real printing. Consent and lifecycle tests for M4."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from m4_print_gate import GateError, PrintGate


@pytest.fixture
def preview(tmp_path):
    f = tmp_path / "sample_preview.png"
    f.write_bytes(b"test only; never sent to printer")
    return f


def verified(preview):
    gate = PrintGate()
    gate.begin_manual_test("Canon MF244dw", preview)
    gate.manual_submitted()
    gate.confirm_paper(paper_present=True, exactly_one=True, image_ok=True)
    return gate


def test_begins_unarmed_even_if_previous_preferences_exist():
    gate = PrintGate()
    assert not gate.armed
    assert not gate.will_submit("Canon MF244dw")
    with pytest.raises(GateError, match="PHYSICAL_TRIAL"):
        gate.arm("Canon MF244dw", explicit_confirmation=True)


def test_no_arming_without_completed_paper_check(preview):
    gate = PrintGate()
    gate.begin_manual_test("Canon MF244dw", preview)
    with pytest.raises(GateError, match="TEST_NOT_VERIFIED"):
        gate.arm("Canon MF244dw", explicit_confirmation=True)
    gate.manual_submitted()
    with pytest.raises(GateError, match="TEST_NOT_VERIFIED"):
        gate.arm("Canon MF244dw", explicit_confirmation=True)


def test_successful_manual_proof_enables_only_exact_queue(preview):
    gate = verified(preview)
    with pytest.raises(GateError, match="NO_EXPLICIT_PERMISSION"):
        gate.arm("Canon MF244dw", explicit_confirmation=False)
    gate.arm("Canon MF244dw", explicit_confirmation=True)
    assert gate.will_submit("Canon MF244dw")
    assert not gate.will_submit("Some other printer")


def test_failed_test_never_enables_arming(preview):
    gate = PrintGate()
    gate.begin_manual_test("Canon MF244dw", preview)
    gate.manual_failed()
    assert not gate.will_submit("Canon MF244dw")
    with pytest.raises(GateError, match="PHYSICAL_TRIAL"):
        gate.arm("Canon MF244dw", explicit_confirmation=True)


@pytest.mark.parametrize("present,copies,image_ok", [
    (False, True, True), (True, False, True), (True, True, False)
])
def test_any_failed_paper_condition_blocks_arming(preview, present, copies, image_ok):
    gate = PrintGate()
    gate.begin_manual_test("Canon MF244dw", preview)
    gate.manual_submitted()
    gate.confirm_paper(paper_present=present, exactly_one=copies, image_ok=image_ok)
    with pytest.raises(GateError, match="PHYSICAL_TRIAL"):
        gate.arm("Canon MF244dw", explicit_confirmation=True)


def test_queue_change_revokes_permission(preview):
    gate = verified(preview)
    gate.arm("Canon MF244dw", explicit_confirmation=True)
    gate.set_printer("Generic Printer")
    assert not gate.will_submit("Canon MF244dw")
    gate.set_printer("Canon MF244dw")
    with pytest.raises(GateError, match="PHYSICAL_TRIAL"):
        gate.arm("Canon MF244dw", explicit_confirmation=True)


def test_stop_and_restart_disarms(preview):
    gate = verified(preview)
    gate.arm("Canon MF244dw", explicit_confirmation=True)
    gate.disarm()
    assert not gate.will_submit("Canon MF244dw")
    gate.arm("Canon MF244dw", explicit_confirmation=True)
    gate.reset_for_new_process()
    assert not gate.armed
    assert gate.verified_printer is None


def test_new_manual_test_clears_old_proof(preview):
    gate = verified(preview)
    gate.begin_manual_test("Canon MF244dw", preview)
    assert gate.verified_printer is None
    with pytest.raises(GateError, match="TEST_NOT_VERIFIED"):
        gate.arm("Canon MF244dw", explicit_confirmation=True)


def test_invalid_or_missing_preview_cannot_be_sent(tmp_path):
    gate = PrintGate()
    with pytest.raises(GateError):
        gate.begin_manual_test("Canon MF244dw", tmp_path / "missing.png")
    f = tmp_path / "not_image.pdf"
    f.write_bytes(b"test")
    with pytest.raises(GateError):
        gate.begin_manual_test("Canon MF244dw", f)


def test_cannot_begin_duplicate_manual_print(preview):
    gate = PrintGate()
    gate.begin_manual_test("Canon MF244dw", preview)
    with pytest.raises(GateError, match="ALREADY_TESTING"):
        gate.begin_manual_test("Canon MF244dw", preview)
