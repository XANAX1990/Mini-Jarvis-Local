"""Preset models, used both for presets.json and for the web API (SECURITY.md: "Presets written from the web").

Structural rules live here (types, lengths, absolute paths, URL and URI schemes). Whether a file
exists is checked separately by `missing_paths`, only when a preset is saved from the web: an app
that was uninstalled must not stop Jarvis from starting.
"""
import os
import re
from pathlib import PureWindowsPath
from typing import Annotated, Literal, Union
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, StrictStr, StringConstraints, field_validator

from jarvis.matcher import normalize

NAME_PATTERN = r"^[a-z0-9-]{1,32}$"
Name = Annotated[str, StringConstraints(pattern=NAME_PATTERN)]

BLOCKED_URI_SCHEMES = {"file", "javascript", "vbscript", "data", "shell", "search-ms", "ms-msdt"}
# at least two characters: a single letter is a drive (C:\\...), which would start any file path
URI_SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.-]+:")
PERIODS = ("today", "week", "month")

# Programs that run other commands, and script files. A preset written from the web may not start them:
# with `run` plus args they turn "start a program" into "run any command". Best effort (a renamed copy
# gets past it); presets.json itself is yours to edit, so loading the file does not apply this.
SHELLS = {
    "cmd.exe", "powershell.exe", "powershell_ise.exe", "pwsh.exe", "wscript.exe", "cscript.exe", "mshta.exe",
    "rundll32.exe", "regsvr32.exe", "msiexec.exe", "wmic.exe", "certutil.exe", "bitsadmin.exe", "bash.exe",
    "wsl.exe", "wt.exe", "forfiles.exe", "msbuild.exe", "installutil.exe", "cmstp.exe", "schtasks.exe",
    "reg.exe", "sc.exe",
}
SCRIPT_SUFFIXES = {
    ".bat", ".cmd", ".ps1", ".psm1", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".wsh", ".hta", ".msi", ".scr",
    ".reg", ".com", ".pif", ".cpl",
}
BLOCKED_PROGRAM = "programs that run other commands (shells, script hosts) are not allowed from the web"
BLOCKED_SCRIPT = "script files are not allowed from the web"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _unquote(value):
    """'Copy as path' puts quotes around the path: strip them."""
    if isinstance(value, str):
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] == '"':
            value = value[1:-1].strip()
    return value


def _clean(value):
    if any(ord(c) < 32 for c in value):
        raise ValueError("must not contain control characters")
    return value


def _absolute(value):
    _clean(value)
    if not PureWindowsPath(os.path.expandvars(value)).is_absolute():
        raise ValueError("must be an absolute path")
    return value


class RunAction(_Model):
    type: Literal["run"]
    path: StrictStr = Field(min_length=1, max_length=500)
    args: list[Annotated[StrictStr, Field(max_length=500)]] = Field(default_factory=list, max_length=20)

    @field_validator("path", mode="before")
    @classmethod
    def _unquote_path(cls, value):
        return _unquote(value)

    @field_validator("path")
    @classmethod
    def _exe(cls, value):
        _absolute(value)
        if not value.lower().endswith(".exe"):
            raise ValueError("must be an .exe file")
        return value


class OpenAction(_Model):
    type: Literal["open"]
    target: StrictStr = Field(min_length=1, max_length=500)

    @field_validator("target", mode="before")
    @classmethod
    def _unquote_target(cls, value):
        return _unquote(value)

    @field_validator("target")
    @classmethod
    def _absolute_target(cls, value):
        return _absolute(value)


class UriAction(_Model):
    type: Literal["uri"]
    target: StrictStr = Field(min_length=1, max_length=500)

    @field_validator("target")
    @classmethod
    def _scheme(cls, value):
        _clean(value)
        found = URI_SCHEME.match(value)
        if not found:
            raise ValueError("must start with a scheme such as discord:")
        scheme = found.group()[:-1].lower()
        if scheme in BLOCKED_URI_SCHEMES or scheme.startswith("ms-"):
            raise ValueError(f"the '{scheme}:' scheme is not allowed")
        return value


class ChromeAction(_Model):
    type: Literal["chrome"]
    urls: list[Annotated[StrictStr, Field(min_length=1, max_length=2000)]] = Field(min_length=1, max_length=20)

    @field_validator("urls")
    @classmethod
    def _http_only(cls, values):
        for url in values:
            if re.search(r"\s", url):
                raise ValueError("a URL must not contain spaces")
            parts = urlsplit(url)
            if parts.scheme.lower() not in ("http", "https") or not parts.netloc:
                raise ValueError("only http:// and https:// URLs are allowed")
        return values


class WaitAction(_Model):
    type: Literal["wait"]
    seconds: Union[StrictInt, StrictFloat] = Field(ge=0, le=30)


class SpendingAction(_Model):
    type: Literal["spending"]
    period: Literal["today", "week", "month"]


Action = Annotated[
    Union[RunAction, OpenAction, UriAction, ChromeAction, WaitAction, SpendingAction],
    Field(discriminator="type"),
]


class Preset(_Model):
    phrases: list[Annotated[StrictStr, Field(min_length=1, max_length=100)]] = Field(min_length=1, max_length=20)
    reply: StrictStr = Field(max_length=200)
    actions: list[Action] = Field(max_length=20)

    @field_validator("phrases")
    @classmethod
    def _speakable(cls, values):
        values = [v.strip() for v in values]
        if not all(normalize(v) for v in values):
            raise ValueError("every phrase needs at least one letter or digit")
        return values


class PresetCreate(Preset):
    name: Name


# What the web editor builds its form from (GET /api/action-types): a new type needs one entry here.
# field kinds: path | text | text-list | number | choice
ACTION_TYPES = [
    {"type": "run", "label": "เปิดโปรแกรม", "fields": [
        {"name": "path", "kind": "path", "required": True},
        {"name": "args", "kind": "text-list", "required": False}]},
    {"type": "open", "label": "เปิดไฟล์/โฟลเดอร์/shortcut", "fields": [
        {"name": "target", "kind": "path", "required": True}]},
    {"type": "uri", "label": "ลิงก์แอป", "fields": [
        {"name": "target", "kind": "text", "required": True}]},
    {"type": "chrome", "label": "Chrome", "fields": [
        {"name": "urls", "kind": "text-list", "required": True}]},
    {"type": "wait", "label": "รอ", "fields": [
        {"name": "seconds", "kind": "number", "required": True, "min": 0, "max": 30}]},
    {"type": "spending", "label": "ถามยอดใช้จ่าย", "fields": [
        {"name": "period", "kind": "choice", "required": True, "options": list(PERIODS)}]},
]


def _resolved(path):
    """The expanded path as Windows will see it: symlinks and short names resolved, trailing dots/spaces
    dropped (Windows ignores them, so 'cmd.exe.' is cmd.exe)."""
    expanded = os.path.expandvars(path).rstrip(" .")
    return PureWindowsPath(os.path.realpath(expanded) if os.path.exists(expanded) else expanded)


def blocked_programs(preset):
    """(field, message) for each step that would start a shell, a script host or a script file."""
    problems = []
    for i, action in enumerate(preset.actions):
        if action.type == "run":
            if _resolved(action.path).name.lower() in SHELLS:
                problems.append((f"actions.{i}.path", BLOCKED_PROGRAM))
        elif action.type == "open":
            target = _resolved(action.target)
            if target.name.lower() in SHELLS:
                problems.append((f"actions.{i}.target", BLOCKED_PROGRAM))
            elif target.suffix.lower() in SCRIPT_SUFFIXES:
                problems.append((f"actions.{i}.target", BLOCKED_SCRIPT))
    return problems


def missing_paths(preset):
    """(field, message) for each run/open path that does not exist. Messages never echo the path."""
    problems = []
    for i, action in enumerate(preset.actions):
        if action.type == "run" and not os.path.isfile(os.path.expandvars(action.path)):
            problems.append((f"actions.{i}.path", "file not found"))
        elif action.type == "open" and not os.path.exists(os.path.expandvars(action.target)):
            problems.append((f"actions.{i}.target", "path not found"))
    return problems
