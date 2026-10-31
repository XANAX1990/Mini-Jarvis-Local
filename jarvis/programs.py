"""programs.json: the apps a preset's `app` step may open (an allow-list).

A preset names an entry (`{"type": "app", "name": "discord"}`); what the entry starts lives here, and only here:

    "discord": {"kind": "exe", "path": "C:\\...\\Update.exe", "args": ["--processStart", "Discord.exe"]}
    "roblox":  {"kind": "uri", "uri": "roblox:"}

Writing this file from the web (adding or changing an entry) needs a Yes/No box on the desktop (confirm.py);
editing it by hand needs nothing, because whoever can edit the file can already run anything as the owner.

programs.json is the owner's and git-ignored; programs.example.json is the tracked starter.
"""
import json
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath

from pydantic import TypeAdapter, ValidationError

from jarvis.models import Name, Program, UriProgram

PROGRAMS_PATH = Path(__file__).resolve().parent.parent / "programs.json"
EXAMPLE_PATH = PROGRAMS_PATH.with_name("programs.example.json")

_PROGRAMS = TypeAdapter(dict[Name, Program])
# stems that say nothing about the program: use the folder name too ("Discord\\Update.exe" -> discord-update)
_GENERIC_STEMS = {"update", "updater", "launcher", "start", "run", "setup", "app", "main"}


class ProgramError(Exception):
    """Invalid programs file."""


def _with_kind(data):
    """An entry from before `kind` existed (it has a path) is an exe."""
    if not isinstance(data, dict):
        return data
    return {
        name: ({"kind": "exe", **entry} if isinstance(entry, dict) and "kind" not in entry and "path" in entry else entry)
        for name, entry in data.items()
    }


def validate_programs(data):
    """Return `data` as plain dicts if valid ({name: {kind, ...}}), else raise ProgramError. {} is valid."""
    if not isinstance(data, dict):
        raise ProgramError("programs file must be an object of programs")
    try:
        models = _PROGRAMS.validate_python(_with_kind(data))
    except ValidationError as e:
        first = e.errors()[0]
        where = ".".join(str(p) for i, p in enumerate(first["loc"]) if p != "[key]" and not (i == 1 and p in ("exe", "uri")))
        raise ProgramError(f"programs.json: {where or 'programs'}: {first['msg'].removeprefix('Value error, ')}") from None
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


def describe(entry):
    """An entry as the person should see it before saying yes: for an exe the path Windows will really
    start (variables and links resolved) and every argument; for a link, the link in full."""
    if entry["kind"] == "uri":
        return {"kind": "uri", "uri": entry["uri"]}
    expanded = os.path.expandvars(entry["path"])
    real = os.path.realpath(expanded) if os.path.exists(expanded) else expanded
    return {"kind": "exe", "path": real, "args": list(entry["args"])}


# ---- the one-time migration of older steps ----

def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _unique(stem, taken):
    stem = stem[:32].strip("-") or "program"
    name, n = stem, 2
    while name in taken:
        suffix = f"-{n}"
        name = stem[: 32 - len(suffix)].strip("-") + suffix
        n += 1
    return name


def program_name(path, taken):
    """A readable, unique name for an exe: its file name, plus its folder when the file name is generic."""
    exe = PureWindowsPath(os.path.expandvars(path))
    stem = _slug(exe.stem) or "program"
    if stem in _GENERIC_STEMS and exe.parent.name:
        stem = _slug(f"{exe.parent.name}-{exe.stem}") or stem
    return _unique(stem, taken)


def uri_name(uri, taken):
    """A name for an app link: its scheme ("roblox:" -> roblox)."""
    return _unique(_slug(uri.split(":", 1)[0]) or "link", taken)


@dataclass
class Migration:
    created: list = field(default_factory=list)  # names of programs it added to programs.json
    steps: int = 0  # steps it rewrote in presets.json

    def __bool__(self):
        return self.steps > 0


def migrate_legacy_steps(presets_path, programs_path=PROGRAMS_PATH):
    """Bring older presets to the `app` step. Runs at every start; does nothing once there is nothing left.

    - `{"type": "run", "path", "args"}` (before programs.json)  -> an exe program + `{"type": "app", "name"}`
    - `{"type": "run", "program": X}` (the first programs.json)  -> `{"type": "app", "name": X}`
    - `{"type": "uri", "target": T}`                              -> a uri program + `{"type": "app", "name"}`
    programs.json is written first, then presets.json (its old version kept as presets.json.bak), so an
    interruption leaves something the next start can finish. The same command or link becomes one program.
    A link that the rules refuse (file:, ms-...) is left as it is, so loading reports it."""
    presets_path = Path(presets_path)
    try:
        presets = json.loads(presets_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Migration()  # missing or broken: load_presets reports it
    if not isinstance(presets, dict):
        return Migration()
    old_steps = [
        (name, i, action)
        for name, preset in presets.items()
        if isinstance(preset, dict) and isinstance(preset.get("actions"), list)
        for i, action in enumerate(preset["actions"])
        if isinstance(action, dict) and action.get("type") in ("run", "uri")
    ]
    if not old_steps:
        return Migration()
    try:
        programs = json.loads(Path(programs_path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        programs = {}
    except (OSError, ValueError):
        raise ProgramError("programs.json is not valid JSON: fix or delete it, then start Jarvis again") from None
    if not isinstance(programs, dict):
        raise ProgramError("programs file must be an object of programs")
    programs = _with_kind(programs)

    by_exe = {
        (p.get("path"), tuple(p.get("args") or ())): n for n, p in programs.items() if isinstance(p, dict) and p.get("kind") == "exe"
    }
    by_uri = {p.get("uri"): n for n, p in programs.items() if isinstance(p, dict) and p.get("kind") == "uri"}
    result = Migration()

    def link(name):
        presets_step = {"type": "app", "name": name}
        result.steps += 1
        return presets_step

    for name, i, action in old_steps:
        step = presets[name]["actions"]
        if action["type"] == "run" and isinstance(action.get("program"), str):
            step[i] = link(action["program"])
        elif action["type"] == "run" and isinstance(action.get("path"), str):
            args = [a for a in action.get("args", []) if isinstance(a, str)]
            key = (action["path"], tuple(args))
            if key not in by_exe:
                new = program_name(action["path"], set(programs))
                programs[new] = {"kind": "exe", "path": action["path"], "args": args}
                by_exe[key] = new
                result.created.append(new)
            step[i] = link(by_exe[key])
        elif action["type"] == "uri" and isinstance(action.get("target"), str):
            target = action["target"]
            try:
                UriProgram.model_validate({"kind": "uri", "uri": target})
            except ValidationError:
                continue  # refused by the rules: leave the step, loading says why
            if target not in by_uri:
                new = uri_name(target, set(programs))
                programs[new] = {"kind": "uri", "uri": target}
                by_uri[target] = new
                result.created.append(new)
            step[i] = link(by_uri[target])
    if not result.steps:
        return result
    _write_atomic(programs_path, programs, keep_backup=True)
    _write_atomic(presets_path, presets, keep_backup=True)
    return result
