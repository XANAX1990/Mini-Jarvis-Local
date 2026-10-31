"""Ask the person at this PC to confirm something dangerous in a native Yes/No box.

Adding a program to programs.json from the web (a page, or anything that can call the local API) must be
approved here, on the desktop: the box is topmost, shows the program's name, its full path and every
argument, and defaults to No. No answer within the timeout is No. Only one box is shown at a time (the
API answers 409 to a second request).
"""
import ctypes
import threading

TIMEOUT_SECONDS = 60
YES, NO, TIMEOUT = "yes", "no", "timeout"

_MB_YESNO = 0x4
_MB_ICONWARNING = 0x30
_MB_DEFBUTTON2 = 0x100  # the default button is No: a stray Enter does not approve
_MB_SETFOREGROUND = 0x10000
_MB_TOPMOST = 0x40000
_IDYES, _IDNO = 6, 7
_WM_COMMAND = 0x111
FLAGS = _MB_YESNO | _MB_ICONWARNING | _MB_DEFBUTTON2 | _MB_SETFOREGROUND | _MB_TOPMOST

TITLE = "Jarvis: ยืนยันการเพิ่มโปรแกรม"


def program_text(name, path, args, timeout=TIMEOUT_SECONDS):
    """What the box says. `path` should be the path that will really be started."""
    shown = "\n".join(f'    "{a}"' for a in args) if args else "    (ไม่มี)"
    return (
        "มีคำขอเพิ่มโปรแกรมที่ Jarvis จะเปิดได้ (จากหน้าเว็บหรือ API ของ Jarvis)\n\n"
        f"ชื่อ: {name}\n"
        f"ไฟล์: {path}\n"
        f"อาร์กิวเมนต์:\n{shown}\n\n"
        "กด Yes เฉพาะเมื่อคุณเป็นคนสั่งเพิ่มเอง และรู้จักโปรแกรมนี้\n"
        f"กด No หรือไม่ตอบใน {timeout} วินาที = ไม่เพิ่ม"
    )


class _Win32:
    """The few Win32 calls we need. Tests replace this with a fake."""

    def __init__(self):
        from ctypes import wintypes

        self._wintypes = wintypes
        self.user32 = ctypes.windll.user32
        self.kernel32 = ctypes.windll.kernel32
        self._enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        self.user32.MessageBoxW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.UINT]
        self.user32.MessageBoxW.restype = ctypes.c_int
        self.user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        self.user32.PostMessageW.restype = wintypes.BOOL
        self.user32.EnumThreadWindows.argtypes = [wintypes.DWORD, self._enum_proc, wintypes.LPARAM]
        self.user32.EnumThreadWindows.restype = wintypes.BOOL
        self.kernel32.GetCurrentThreadId.restype = wintypes.DWORD

    def thread_id(self):
        return self.kernel32.GetCurrentThreadId()

    def message_box(self, text, title, flags):
        return self.user32.MessageBoxW(None, text, title, flags)

    def press_no(self, thread_id):
        """Close the box that thread is showing, as if No was clicked."""

        def press(hwnd, _):
            self.user32.PostMessageW(hwnd, _WM_COMMAND, _IDNO, 0)
            return True

        callback = self._enum_proc(press)  # keep a reference alive for the duration of the call
        self.user32.EnumThreadWindows(thread_id, callback, 0)


def ask(text, title=TITLE, timeout=TIMEOUT_SECONDS, backend=None):
    """Show the box and return YES, NO or TIMEOUT. Blocks until one of them.

    MessageBoxW has no timeout of its own, so it runs in a helper thread; when the time is up the box is
    closed with No. A box that cannot be closed is ignored: its answer no longer matters."""
    backend = backend or _Win32()
    answer = {}
    started, finished = threading.Event(), threading.Event()

    def show():
        answer["thread"] = backend.thread_id()
        started.set()
        answer["result"] = backend.message_box(text, title, FLAGS)
        finished.set()

    threading.Thread(target=show, name="jarvis-confirm", daemon=True).start()
    started.wait(5)
    if finished.wait(timeout):
        return YES if answer.get("result") == _IDYES else NO
    backend.press_no(answer["thread"])
    finished.wait(5)
    return TIMEOUT


def ask_program(name, path, args, timeout=TIMEOUT_SECONDS):
    """The confirmation for adding a program: YES, NO or TIMEOUT."""
    return ask(program_text(name, path, args, timeout), timeout=timeout)
