"""programs.json: the programs a preset's `run` step may start (an allow-list).

A preset names a program (`{"type": "run", "program": "discord"}`); the path and arguments live here, and
only here. Writing this file from the web needs a Yes/No box on the desktop (confirm.py); editing it by hand
needs nothing, because whoever can edit the file can already run anything as the owner.

programs.json is the owner's and git-ignored; programs.example.json is the tracked starter.
"""
import json
import os
import re
import shutil
from pathlib import Path, PureWindowsPath

from pydantic import TypeAdapter, ValidationError

from jarvis.models import Name, Program

PROGRAMS_PATH = Path(__file__).resolve().parent.parent / "programs.json"
EXAMPLE_PATH = PROGRAMS_PATH.with_name("programs.example.json")

_PROGRAMS = TypeAdapter(dict[Name, Program])
# stems that say nothing about the program: use the folder name too ("Discord\\Update.exe" -> discord-update)
_GENERIC_STEMS = {"update", "updater", "launcher", "start", "run", "setup", "app", "main"}


class ProgramError(Exception):
    """Invalid programs file."""


def validate_programs(data):
    """Return `data` as plain dicts {name: {path, args}} if valid, else raise ProgramError. {} is valid."""
    if not isinstance(data, dict):
        raise ProgramError("programs file must be an object of programs")
    try:
        models = _PROGRAMS.validate_python(data)
    except ValidationError as e:
        first = e.errors()[0]
        where = ".".join(str(p) for p in first["loc"] if p != "[key]") or "programs"
        raise ProgramError(f"programs.json: {where}: {first['msg'].removeprefix('Value error, ')}") from None
    return {name: program.model_dump() for name, program in models.items()}


def load_programs(path=PROGRAMS_PATH):
    """The programs, or {} if there is no file yet."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as e:
        raise ProgramError(f"programs file is not valid JSON: {e}") from None
    return validate_programs(data)


def ensure_programs_file(path=PROGRAMS_PATH, example=EXAMPLE_PATH):
    """First run: start from the example. True if created. An existing file is never touched."""
    path, example = Path(path), Path(example)
    if path.exists() or not example.is_file():
        return False
    shutil.copyfile(example, path)
    return True


def _write_atomic(path, data, keep_backup):
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        if keep_backup and path.exists():
            shutil.copyfile(path, path.with_name(path.name + ".bak"))
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


class ProgramStore:
    """The current programs, and atomic saves (a .tmp file, the old file kept as .bak, then os.replace)."""

    def __init__(self, path=PROGRAMS_PATH):
        self.path = Path(path)
        self.programs = {}

    def load(self):
        self.programs = load_programs(self.path)
        return self.programs

    def save(self, programs):
        _write_atomic(self.path, programs, keep_backup=True)
        self.programs = programs


def describe(program):
    """A program as the person should see it before saying yes: the path Windows will really start, and
    every argument."""
    expanded = os.path.expandvars(program["path"])
    real = os.path.realpath(expanded) if os.path.exists(expanded) else expanded
    return real, list(program["args"])


# ---- one-time migration of `run` steps that still carry their own path and args ----

def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def program_name(path, taken):
    """A readable, unique name for a program: its file name, plus its folder when the file name is generic."""
    exe = PureWindowsPath(os.path.expandvars(path))
    stem = _slug(exe.stem) or "program"
    if stem in _GENERIC_STEMS and exe.parent.name:
        stem = _slug(f"{exe.parent.name}-{exe.stem}") or stem
    stem = stem[:32].strip("-") or "program"
    name, n = stem, 2
    while name in taken:
        suffix = f"-{n}"
        name = stem[: 32 - len(suffix)].strip("-") + suffix
        n += 1
    return name


def migrate_legacy_runs(presets_path, programs_path=PROGRAMS_PATH):
    """Move `run` steps with their own path/args into programs.json. Returns the new program names.

    Runs at every start and does nothing once there is nothing left to move. programs.json is written
    first, then presets.json (its old version is kept as presets.json.bak), so an interruption leaves
    something the next start can finish. The same path and args become one program."""
    presets_path = Path(presets_path)
    try:
        presets = json.loads(presets_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []  # missing or broken: load_presets reports it
    if not isinstance(presets, dict):
        return []
    legacy = [
        (name, i, action)
        for name, preset in presets.items()
        if isinstance(preset, dict) and isinstance(preset.get("actions"), list)
        for i, action in enumerate(preset["actions"])
        if isinstance(action, dict) and action.get("type") == "run" and isinstance(action.get("path"), str)
    ]
    if not legacy:
        return []
    try:
        programs = json.loads(Path(programs_path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        programs = {}
    except (OSError, ValueError):
        raise ProgramError("programs.json is not valid JSON: fix or delete it, then start Jarvis again") from None
    if not isinstance(programs, dict):
        raise ProgramError("programs file must be an object of programs")

    by_command = {
        (p.get("path"), tuple(p.get("args") or ())): name for name, p in programs.items() if isinstance(p, dict)
    }
    created = []
    for name, i, action in legacy:
        args = [a for a in action.get("args", []) if isinstance(a, str)]
        key = (action["path"], tuple(args))
        if key not in by_command:
            new = program_name(action["path"], set(programs))
            programs[new] = {"path": action["path"], "args": args}
            by_command[key] = new
            created.append(new)
        presets[name]["actions"][i] = {"type": "run", "program": by_command[key]}
    _write_atomic(programs_path, programs, keep_backup=True)
    _write_atomic(presets_path, presets, keep_backup=True)
    return created
