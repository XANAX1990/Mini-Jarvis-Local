"""Registers the one configured hotkey with the keyboard library.

SECURITY.md: only the configured hotkey is registered; no other key press is read, logged or stored.
The key is suppressed, so it does not reach other programs (Caps Lock no longer toggles caps).
"""
import threading


class Hotkeys:
    def __init__(self, keyboard=None):
        self._keyboard = keyboard
        self._handle = None
        self._key = None

    def _kb(self):
        if self._keyboard is None:
            import keyboard

            self._keyboard = keyboard
        return self._keyboard

    def apply(self, key, callback):
        """Make `key` the only registered hotkey; None unregisters it (the key works normally again)."""
        if self._handle is not None and key == self._key:
            return
        self.clear()
        if key is None:
            return
        self._handle = self._kb().add_hotkey(key, callback, suppress=True)
        self._key = key

    def check(self, key):
        return check(key, self._keyboard)

    def clear(self):
        if self._handle is not None:
            self._kb().remove_hotkey(self._handle)
        self._handle = self._key = None


def _keyboard():
    import keyboard

    return keyboard


def check(key, keyboard=None):
    """None if the keyboard library understands `key`, else a short reason."""
    try:
        (keyboard or _keyboard()).parse_hotkey(key)
    except Exception:
        return "this key name is not recognized"
    return None


def capture(timeout=10.0, keyboard=None):
    """Wait for the next key combo and return its name (None on timeout). Nothing is saved.

    SECURITY.md: only the keys of this one combo are looked at, until the first key is released;
    nothing is logged or stored, and the hook is removed before returning."""
    kb = keyboard or _keyboard()
    pressed = []
    done = threading.Event()

    def on_event(event):
        if done.is_set():
            return
        if event.event_type == "down":
            if event.name not in pressed:
                pressed.append(event.name)
        elif pressed:
            done.set()

    hook = kb.hook(on_event)
    try:
        done.wait(timeout)
    finally:
        kb.unhook(hook)
    return kb.get_hotkey_name(pressed) if done.is_set() else None
