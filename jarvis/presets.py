"""Load + validate presets.json and run preset actions.

Speech only ever selects a preset *name*. Nothing here builds a command from
transcript text: every URL comes from presets.json and every app (program or app link) from programs.json.
"""
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from jarvis.models import Name, Preset

PRESETS_PATH = Path(__file__).resolve().parent.parent / "presets.json"
EXAMPLE_PATH = PRESETS_PATH.with_name("presets.example.json")  # tracked starter; presets.json is yours and git-ignored

CHROME_CANDIDATES = [
    r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
    r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
    r"%LocalAppData%\Google\Chrome\Application\chrome.exe",
]


class PresetError(Exception):
    """Invalid presets file or unknown preset name."""


_PRESETS = TypeAdapter(dict[Name, Preset])
_ACTION_TYPES = {"app", "open", "chrome", "wait", "spending"}


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


def validate_presets(data, programs=None):
    """Return `data` as plain dicts if valid, else raise PresetError with a clear message.

    With `programs` (programs.json), every `app` step must name an entry in it."""
    if not isinstance(data, dict) or not data:
        raise PresetError("presets file must be a non-empty object of presets")
    try:
        models = _PRESETS.validate_python(data)
    except ValidationError as e:
        first = e.errors()[0]
        raise PresetError(describe_error(first["loc"], first["msg"])) from None
    presets = {name: preset.model_dump(exclude_unset=True) for name, preset in models.items()}
    if programs is not None:
        for name, preset in presets.items():
            for i, action in enumerate(preset["actions"], 1):
                if action["type"] == "app" and action["name"] not in programs:
                    raise PresetError(
                        f"preset '{name}' action {i}: app '{action['name']}' is not in programs.json "
                        "(add it on the Programs page, or in programs.json)"
                    )
    return presets


def ensure_presets_file(path=PRESETS_PATH, example=EXAMPLE_PATH):
    """First run: there is no presets.json yet, so start from the example. True if it was created.

    An existing file is never touched, and a missing example is left for load_presets to report."""
    path, example = Path(path), Path(example)
    if path.exists() or not example.is_file():
        return False
    shutil.copyfile(example, path)
    return True


def load_presets(path=PRESETS_PATH, programs=None):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        raise PresetError(f"presets file not found: {path}") from None
    except json.JSONDecodeError as e:
        raise PresetError(f"presets file is not valid JSON: {e}") from None
    return validate_presets(data, programs)


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


def run_action(action, programs=None):
    kind = action["type"]
    if kind == "app":
        name = action.get("name")  # a malformed step must fail, not crash
        entry = (programs or {}).get(name)
        if entry is None:  # only programs.json decides what may start
            raise OSError(f"app '{name}' is not in programs.json")
        if entry["kind"] == "uri":
            os.startfile(entry["uri"])
        else:
            path = os.path.expandvars(entry["path"])
            args = [os.path.expandvars(a) for a in entry.get("args", [])]
            subprocess.Popen([path, *args])  # list form, never shell=True
    elif kind in ("run", "uri"):  # the old shapes: migrated at start, and never run from a preset
        raise OSError(f"a '{kind}' step is not supported any more: use an app from programs.json")
    elif kind == "open":
        os.startfile(os.path.expandvars(action["target"]))
    elif kind == "chrome":
        subprocess.Popen([_find_chrome(), "--new-window", *action["urls"]])
    elif kind == "wait":
        time.sleep(action["seconds"])
    # "spending" starts nothing: its answer is spoken instead of the reply (see spoken_reply)


def run_preset(presets, name, log=print, programs=None):
    """Run every action in order. A failing action is reported, not fatal."""
    preset = get_preset(presets, name)
    failures = 0
    for i, action in enumerate(preset["actions"], 1):
        try:
            run_action(action, programs)
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
