import threading
import time

from jarvis import confirm

EXE = {"kind": "exe", "path": "C:\\Windows\\System32\\calc.exe", "args": ["--x", "y z"]}
LINK = {"kind": "uri", "uri": "roblox:"}


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


def test_adding_an_exe_shows_the_name_the_path_and_every_argument():
    text = confirm.change_text("calc", None, EXE)
    for needle in ("เพิ่ม", "calc", "โปรแกรม (.exe)", "C:\\Windows\\System32\\calc.exe", '"--x"', '"y z"', "60", "= ไม่เพิ่ม"):
        assert needle in text
    assert "(ไม่มี)" in confirm.change_text("calc", None, {**EXE, "args": []})
    assert "ค่าเดิม" not in text  # nothing to compare when adding


def test_adding_a_link_shows_the_whole_link():
    text = confirm.change_text("roblox", None, LINK)
    assert "ลิงก์แอป" in text and "ลิงก์: roblox:" in text and "ไฟล์:" not in text


def test_changing_an_app_puts_the_old_value_next_to_the_new_one():
    new = {**EXE, "path": "C:\\Windows\\notepad.exe", "args": ["-p"]}
    text = confirm.change_text("calc", EXE, new, used_by=["game", "work"])
    assert text.index("ค่าเดิม") < text.index("calc.exe") < text.index("ค่าใหม่") < text.index("notepad.exe")
    for needle in ('"--x"', '"y z"', '"-p"', "game, work", "ไม่แก้ (ใช้ค่าเดิมต่อ)", "แก้แอป"):
        assert needle in text


def test_changing_the_kind_shows_both_kinds():
    text = confirm.change_text("calc", EXE, LINK)
    assert "โปรแกรม (.exe)" in text and "ลิงก์แอป" in text and "roblox:" in text


def test_a_change_without_users_does_not_mention_presets():
    assert "preset ที่ใช้แอปนี้" not in confirm.change_text("calc", EXE, LINK)


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


def test_ask_change_passes_the_text_and_the_timeout(monkeypatch):
    seen = {}
    monkeypatch.setattr(confirm, "ask", lambda text, timeout=None, **k: seen.update(text=text, timeout=timeout) or confirm.NO)
    assert confirm.ask_change("calc", None, EXE, timeout=7) == confirm.NO
    assert seen["timeout"] == 7 and "calc" in seen["text"] and "7 วินาที" in seen["text"]
    confirm.ask_change("calc", EXE, LINK, used_by=["game"], timeout=9)
    assert "game" in seen["text"] and "ค่าเดิม" in seen["text"]


def test_the_real_windows_backend_is_wired_correctly():
    """Builds the real ctypes bindings (no box is shown): wrong argument types would fail here, not at 2 a.m."""
    backend = confirm._Win32()
    assert isinstance(backend.thread_id(), int) and backend.thread_id() > 0
    backend.press_no(backend.thread_id())  # this thread has no windows: a harmless no-op
