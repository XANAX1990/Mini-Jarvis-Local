"""settings.json: hotkey, listening thresholds, beeps. Validated on load.

A bad value falls back to its default and is reported through `log`; Jarvis still starts.
settings.json is git-ignored (settings.example.json is the committed template).
"""
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from jarvis.matcher import DEFAULT_THRESHOLD, MIN_THRESHOLD

BOUNDS = {  # (low, high), shared with the web API
    "silence_ms": (300, 5000),
    "min_threshold": (0.001, 0.5),
    "max_seconds": (3, 60),
    "match_threshold": (MIN_THRESHOLD, 100),
}

SETTINGS_PATH = Path(__file__).resolve().parent.parent / "settings.json"

# Single keys that would fire while typing, or vanish from typing once the hotkey is suppressed.
# Any one-character key (letters, digits, punctuation) is refused too.
TYPING_KEYS = {
    "space", "enter", "tab", "backspace", "esc", "escape",
    "shift", "left shift", "right shift",
}
MODIFIERS = {
    "ctrl", "alt", "shift", "windows", "win", "alt gr",
    "left ctrl", "right ctrl", "left alt", "right alt",
    "left shift", "right shift", "left windows", "right windows",
}


def validate_hotkey(text):
    """Return (normalized hotkey, None), or (None, reason) if the key can't be used."""
    if not isinstance(text, str):
        return None, "hotkey must be text"
    parts = [p.strip() for p in text.lower().split("+")]
    if not 1 <= len(parts) <= 4 or not all(p and len(p) <= 20 for p in parts):
        return None, "use one key or a combo like ctrl+alt+j"
    if len(parts) == 1:
        key = parts[0]
        if len(key) == 1 or key in TYPING_KEYS:
            return None, f"'{key}' is a typing key: use it with a modifier, e.g. ctrl+alt+{key}"
    else:
        *held, last = parts
        if not all(p in MODIFIERS for p in held):
            return None, "in a combo, every key before the last must be ctrl, alt, shift or windows"
        if last in MODIFIERS:
            return None, "a combo must end with a normal key, e.g. ctrl+alt+j"
    return "+".join(parts), None


@dataclass(frozen=True)
class Settings:
    hotkey: str = "caps lock"
    armed_on_start: bool = True
    silence_ms: int = 1000
    min_threshold: float = 0.01
    max_seconds: int = 15
    beep: bool = True
    match_threshold: float = DEFAULT_THRESHOLD

    def to_dict(self):
        return asdict(self)


def _number(low, high, kind):
    def check(value):
        ok = isinstance(value, (int, float)) and not isinstance(value, bool) and low <= value <= high
        return kind(value) if ok else None

    return check


def _hotkey(value):
    return validate_hotkey(value)[0]


def _flag(value):
    return value if isinstance(value, bool) else None


_CHECKS = {
    "hotkey": _hotkey,
    "armed_on_start": _flag,
    "silence_ms": _number(*BOUNDS["silence_ms"], int),
    "min_threshold": _number(*BOUNDS["min_threshold"], float),
    "max_seconds": _number(*BOUNDS["max_seconds"], int),
    "beep": _flag,
    "match_threshold": _number(*BOUNDS["match_threshold"], float),
}


def parse_settings(data, log=print):
    """Settings from a decoded JSON object; every invalid or unknown key is logged and defaulted."""
    if not isinstance(data, dict):
        log("settings.json must be an object - using defaults")
        return Settings()
    values = {}
    for key, value in data.items():
        check = _CHECKS.get(key)
        if check is None:
            log(f"settings.json: unknown key {key!r} ignored")
            continue
        checked = check(value)
        if checked is None:
            log(f"settings.json: invalid value for {key!r} - using the default")
        else:
            values[key] = checked
    return Settings(**values)


def load_settings(path=SETTINGS_PATH, log=print):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return Settings()
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        log("settings.json could not be read - using defaults")
        return Settings()
    return parse_settings(data, log)


def save_settings(settings, path=SETTINGS_PATH):
    """Write settings.json atomically (.tmp + os.replace)."""
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(json.dumps(settings.to_dict(), indent=2) + "\n", encoding="utf-8", newline="\n")
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
