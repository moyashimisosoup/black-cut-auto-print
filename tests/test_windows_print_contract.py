"""Exercise GDI adapter against strict fakes. Does not open real printers."""
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from PIL import Image, ImageWin

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import windows_print


class FakeMode:
    Fields = 0
    PaperSize = 0
    Orientation = 0
    Copies = 0
    Duplex = 0
    Color = 0


class FakePrintState:
    def __init__(self, monkeypatch, *, page=(2480, 3508), status=0):
        self.calls = []
        self.mode = FakeMode()
        constants = dict(DM_PAPERSIZE=1, DM_ORIENTATION=2, DM_COPIES=4,
                         DM_DUPLEX=8, DM_COLOR=16, DMPAPER_A4=9,
                         DMORIENT_PORTRAIT=1, DMORIENT_LANDSCAPE=2,
                         DMDUP_SIMPLEX=1, DMCOLOR_MONOCHROME=1,
                         PHYSICALWIDTH=101, PHYSICALHEIGHT=102,
                         PHYSICALOFFSETX=103, PHYSICALOFFSETY=104,
                         HORZRES=105, VERTRES=106,
                         LOGPIXELSX=107, LOGPIXELSY=108)
        self.con = SimpleNamespace(**constants)
        caps = {101: page[0], 102: page[1], 103: 59, 104: 59,
                105: page[0]-118, 106: page[1]-118, 107: 300, 108: 300}
        state = self
        class FakePrint(ModuleType):
            PRINTER_ENUM_LOCAL = 1
            PRINTER_ENUM_CONNECTIONS = 2
            PRINTER_STATUS_OFFLINE = 1
            PRINTER_STATUS_PAUSED = 2
            PRINTER_STATUS_ERROR = 4
            PRINTER_STATUS_PAPER_OUT = 8
            def EnumPrinters(self, flags):
                return [(0, None, 'Canon MF244dw', None)]
            def OpenPrinter(self, name):
                state.calls.append('open')
                return 123
            def GetPrinter(self, handle, level):
                return {'Status': status, 'pDevMode': state.mode}
            def ClosePrinter(self, handle):
                state.calls.append('close')
            def GetDeviceCaps(self, hdc, code):
                return caps[code]
            def StartDoc(self, hdc, job):
                state.calls.append('startdoc')
                return 345
            def StartPage(self, hdc):
                state.calls.append('startpage')
            def EndPage(self, hdc):
                state.calls.append('endpage')
            def EndDoc(self, hdc):
                state.calls.append('enddoc')
            def AbortDoc(self, hdc):
                state.calls.append('abort')

        class FakeGui(ModuleType):
            def CreateDC(self, *args):
                # Deliberately strict! pywin32 supports EXACTLY three args.
                assert len(args) == 3, f'CreateDC signature incorrect: {args}'
                assert args[0:2] == ('WINSPOOL', 'Canon MF244dw')
                assert args[2] is state.mode
                state.calls.append('createdc')
                return 456
            def DeleteDC(self, handle):
                state.calls.append('deletedc')

        monkeypatch.setitem(sys.modules, 'win32print', FakePrint('win32print'))
        monkeypatch.setitem(sys.modules, 'win32gui', FakeGui('win32gui'))
        monkeypatch.setitem(sys.modules, 'win32con', self.con)
        # Test Windows branch without changing os.name used by other packages.
        monkeypatch.setattr(windows_print, 'os', SimpleNamespace(name='nt'))
        class FakeDib:
            def __init__(self, image):
                pass
            def draw(self, hdc, rect):
                state.calls.append(('draw', rect))
        monkeypatch.setattr(ImageWin, 'Dib', FakeDib)


def _image(tmp_path):
    p = tmp_path / 'a4.png'
    Image.new('RGB', (1240, 1754), 'white').save(p)
    return p


def test_gdi_contract_three_arguments_and_one_job(monkeypatch, tmp_path):
    state = FakePrintState(monkeypatch)
    job = windows_print.submit_a4(_image(tmp_path), 'Canon MF244dw')
    assert job == 345
    assert state.mode.PaperSize == 9
    assert state.mode.Copies == 1 and state.mode.Duplex == 1
    assert state.calls == ['open', 'createdc', 'startdoc', 'startpage',
                           ('draw', (-59, -59, 2421, 3449)), 'endpage',
                           'enddoc', 'deletedc', 'close']


def test_offline_printer_rejected_before_device_context(monkeypatch, tmp_path):
    state = FakePrintState(monkeypatch, status=1)
    with pytest.raises(windows_print.PrinterError, match='OFFLINE'):
        windows_print.submit_a4(_image(tmp_path), 'Canon MF244dw')
    assert state.calls == ['open', 'close']


def test_a3_driver_settings_rejected_before_print_start(monkeypatch, tmp_path):
    state = FakePrintState(monkeypatch, page=(3508, 4961))
    with pytest.raises(windows_print.PrinterError, match='SELECT_A4'):
        windows_print.submit_a4(_image(tmp_path), 'Canon MF244dw')
    assert 'startdoc' not in state.calls
    assert 'deletedc' in state.calls and 'close' in state.calls
