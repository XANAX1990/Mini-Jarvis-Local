"""Load + validate presets.json and run preset actions.

Speech only ever selects a preset *name*. Nothing here builds a command from
transcript text: every path/URL comes from presets.json.
"""
import json
import os
import subprocess
import time
from pathlib import Path

PRESETS_PATH = Path(__file__).resolve().parent.parent / "presets.json"

CHROME_CANDIDATES = [
    r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
    r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
    r"%LocalAppData%\Google\Chrome\Application\chrome.exe",
]

# action type -> (required field, expected type)
_REQUIRED = {
    "run": ("path", str),
    "open": ("target", str),
    "uri": ("target", str),
    "chrome": ("urls", list),
    "wait": ("seconds", (int, float)),
}


class PresetError(Exception):
    """Invalid presets file or unknown preset name."""


def _validate_action(where, action):
    if not isinstance(action, dict):
        raise PresetError(f"{where}: action must be an object")
    kind = action.get("type")
    if kind not in _REQUIRED:
        raise PresetError(
            f"{where}: unknown action type {kind!r} (expected one of {', '.join(_REQUIRED)})"
        )
    field, expected = _REQUIRED[kind]
    if field not in action:
        raise PresetError(f"{where}: '{kind}' action is missing '{field}'")
    value = action[field]
    if isinstance(value, bool) or not isinstance(value, expected):
        raise PresetError(f"{where}: '{field}' has the wrong type")
    if kind == "wait" and value < 0:
        raise PresetError(f"{where}: 'seconds' must be >= 0")
    if kind == "chrome":
        if not value or not all(isinstance(u, str) and u for u in value):
            raise PresetError(f"{where}: 'urls' must be a non-empty list of strings")
    if kind == "run":
        args = action.get("args", [])
        if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
            raise PresetError(f"{where}: 'args' must be a list of strings")


def validate_presets(data):
    """Return `data` if valid, else raise PresetError with a clear message."""
    if not isinstance(data, dict) or not data:
        raise PresetError("presets file must be a non-empty object of presets")
    for name, preset in data.items():
        if not isinstance(preset, dict):
            raise PresetError(f"preset '{name}': must be an object")
        phrases = preset.get("phrases")
        if not isinstance(phrases, list) or not phrases or not all(
            isinstance(p, str) and p.strip() for p in phrases
        ):
            raise PresetError(f"preset '{name}': 'phrases' must be a non-empty list of strings")
        if not isinstance(preset.get("reply"), str):
            raise PresetError(f"preset '{name}': 'reply' must be a string")
        actions = preset.get("actions")
        if not isinstance(actions, list):
            raise PresetError(f"preset '{name}': 'actions' must be a list")
        for i, action in enumerate(actions, 1):
            _validate_action(f"preset '{name}' action {i}", action)
    return data


def load_presets(path=PRESETS_PATH):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        raise PresetError(f"presets file not found: {path}") from None
    except json.JSONDecodeError as e:
        raise PresetError(f"presets file is not valid JSON: {e}") from None
    return validate_presets(data)


def get_preset(presets, name):
    if name not in presets:
        raise PresetError(f"unknown preset '{name}' (available: {', '.join(presets)})")
    return presets[name]


def _find_chrome():
    for candidate in CHROME_CANDIDATES:
        path = os.path.expandvars(candidate)
        if os.path.isfile(path):
            return path
    raise OSError("Chrome not found in the usual install locations")


def run_action(action):
    kind = action["type"]
    if kind == "run":
        path = os.path.expandvars(action["path"])
        args = [os.path.expandvars(a) for a in action.get("args", [])]
        subprocess.Popen([path, *args])  # list form, never shell=True
    elif kind in ("open", "uri"):
        os.startfile(os.path.expandvars(action["target"]))
    elif kind == "chrome":
        subprocess.Popen([_find_chrome(), "--new-window", *action["urls"]])
    elif kind == "wait":
        time.sleep(action["seconds"])


def run_preset(presets, name, log=print):
    """Run every action in order. A failing action is reported, not fatal."""
    preset = get_preset(presets, name)
    failures = 0
    for i, action in enumerate(preset["actions"], 1):
        try:
            run_action(action)
        except OSError as e:
            failures += 1
            log(f"action {i} ({action['type']}) failed: {e}")
    return failures
