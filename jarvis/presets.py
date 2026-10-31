"""Load + validate presets.json and run preset actions.

Speech only ever selects a preset *name*. Nothing here builds a command from
transcript text: every path/URL comes from presets.json.
"""
import json
import os
import subprocess
import time
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from jarvis.models import Name, Preset

PRESETS_PATH = Path(__file__).resolve().parent.parent / "presets.json"

CHROME_CANDIDATES = [
    r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
    r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
    r"%LocalAppData%\Google\Chrome\Application\chrome.exe",
]


class PresetError(Exception):
    """Invalid presets file or unknown preset name."""


_PRESETS = TypeAdapter(dict[Name, Preset])
_ACTION_TYPES = {"run", "open", "uri", "chrome", "wait", "spending"}


def describe_error(loc, message):
    """One validation error as a short sentence: where it is and what is wrong. Never echoes input."""
    message = message.removeprefix("Value error, ")
    parts = []
    for item in loc:
        if isinstance(item, str) and item in _ACTION_TYPES and parts and isinstance(parts[-1], int):
            continue  # the discriminator tag pydantic adds after the action index
        parts.append(item)
    text = []
    for item in parts:
        if isinstance(item, int):
            text.append(f"[{item + 1}]")
        else:
            text.append(("." if text else "") + item)
    return f"{''.join(text) or 'presets'}: {message}"


def validate_presets(data):
    """Return `data` as plain dicts if valid, else raise PresetError with a clear message."""
    if not isinstance(data, dict) or not data:
        raise PresetError("presets file must be a non-empty object of presets")
    try:
        models = _PRESETS.validate_python(data)
    except ValidationError as e:
        first = e.errors()[0]
        raise PresetError(describe_error(first["loc"], first["msg"])) from None
    return {name: preset.model_dump(exclude_unset=True) for name, preset in models.items()}


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
    # "spending" starts nothing: its answer is spoken instead of the reply (see spoken_reply)


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


def spending_period(preset):
    """The period of the preset's `spending` action, or None if it has none."""
    for action in preset["actions"]:
        if action["type"] == "spending":
            return action["period"]
    return None


def spoken_reply(preset):
    """What to say before running the preset: its fixed reply, or the live spending answer."""
    period = spending_period(preset)
    if period is None:
        return preset["reply"]
    from jarvis import spending

    spending.load_env()
    return spending.answer(period)
