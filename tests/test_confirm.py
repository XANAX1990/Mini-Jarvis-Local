import threading
import time

import pytest

from jarvis import confirm


class FakeBox:
    """Stands in for Windows: records the box, answers, or hangs until it is told to close."""

    def __init__(self, result=None, hang=False):
        self.result, self.hang = result, hang
        self.closed = threading.Event()
        self.pressed = []
        self.shown = None

    def thread_id(self):
        return 4242

    def message_box(self, text, title, flags):
        self.shown = (text, title, flags)
        if self.hang:
            self.closed.wait(5)
            return confirm._IDNO  # what Windows returns once No is pressed
        return self.result

    def press_no(self, thread_id):
        self.pressed.append(thread_id)
        self.closed.set()


def test_the_box_shows_the_name_the_path_and_every_argument():
    text = confirm.program_text("calc", "C:\\Windows\\System32\\calc.exe", ["--x", "y z"])
    for needle in ("calc", "C:\\Windows\\System32\\calc.exe", '"--x"', '"y z"', "60"):
        assert needle in text
    assert "(ไม่มี)" in confirm.program_text("calc", "C:\\a.exe", [])


def test_the_box_is_topmost_a_warning_and_defaults_to_no():
    assert confirm.FLAGS & 0x4  # Yes/No
    assert confirm.FLAGS & 0x100  # the second button, No, is the default
    assert confirm.FLAGS & 0x40000 and confirm.FLAGS & 0x10000  # topmost, foreground
    assert confirm.FLAGS & 0x30 == 0x30  # warning icon


def test_yes_is_yes_and_everything_else_is_no():
    assert confirm.ask("t", backend=FakeBox(result=6)) == confirm.YES
    assert confirm.ask("t", backend=FakeBox(result=7)) == confirm.NO
    assert confirm.ask("t", backend=FakeBox(result=0)) == confirm.NO  # the box failed: not a yes
    assert confirm.ask("t", backend=FakeBox(result=2)) == confirm.NO


def test_no_answer_in_time_closes_the_box_and_is_a_no():
    box = FakeBox(hang=True)
    start = time.monotonic()
    assert confirm.ask("t", timeout=0.2, backend=box) == confirm.TIMEOUT
    assert time.monotonic() - start < 3
    assert box.pressed == [4242]  # it pressed No on the box of that thread
    assert box.shown[2] == confirm.FLAGS


def test_a_fast_answer_does_not_close_anything():
    box = FakeBox(result=6)
    assert confirm.ask("t", timeout=5, backend=box) == confirm.YES
    assert box.pressed == []


def test_ask_program_passes_the_text_and_the_timeout(monkeypatch):
    seen = {}
    monkeypatch.setattr(confirm, "ask", lambda text, timeout=None, **k: seen.update(text=text, timeout=timeout) or confirm.NO)
    assert confirm.ask_program("calc", "C:\\a.exe", ["-x"], timeout=7) == confirm.NO
    assert seen["timeout"] == 7 and "calc" in seen["text"] and "7 วินาที" in seen["text"]


def test_the_real_windows_backend_is_wired_correctly():
    """Builds the real ctypes bindings (no box is shown): wrong argument types would fail here, not at 2 a.m."""
    backend = confirm._Win32()
    assert isinstance(backend.thread_id(), int) and backend.thread_id() > 0
    backend.press_no(backend.thread_id())  # this thread has no windows: a harmless no-op
