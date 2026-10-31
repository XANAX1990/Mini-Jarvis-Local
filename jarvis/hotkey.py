"""Registers the one configured hotkey with the keyboard library.

SECURITY.md: only the configured hotkey is registered; no other key press is read, logged or stored.
The key is suppressed, so it does not reach other programs (Caps Lock no longer toggles caps).
"""


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

    def clear(self):
        if self._handle is not None:
            self._kb().remove_hotkey(self._handle)
        self._handle = self._key = None
