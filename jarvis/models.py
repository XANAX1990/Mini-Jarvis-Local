"""Preset models, used both for presets.json and for the web API (SECURITY.md: "Presets written from the web").

Structural rules live here (types, lengths, absolute paths, URL and URI schemes). Whether a file
exists, and which files `open` may touch, is checked separately (`open_problems`), only when a preset is
saved from the web: an app that was uninstalled must not stop Jarvis from starting.

A `run` step never carries a path or arguments: it names a program from programs.json (an allow-list the
web can only extend after a Yes/No box on the desktop, see confirm.py).
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

# What `open` may open from the web: folders, and documents/media of these types. No shortcuts (.lnk, .url),
# scripts or programs: those would start something.
OPEN_SUFFIXES = (".pdf", ".txt", ".md", ".docx", ".xlsx", ".pptx", ".png", ".jpg", ".jpeg", ".gif", ".mp3", ".mp4")
OPEN_NOT_ALLOWED = "only folders and these files can be opened from the web: pdf, txt, md, docx, xlsx, pptx, png, jpg, jpeg, gif, mp3, mp4"


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


class Program(_Model):
    """An entry of programs.json: what a `run` step may start. Added from the web only after a confirmation."""

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


class ProgramCreate(Program):
    name: Name


class RunAction(_Model):
    type: Literal["run"]
    program: Name  # a key of programs.json; a path or args here are refused (extra fields are forbidden)


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
# field kinds: path | text | text-list | number | choice | program (a name from GET /api/programs)
ACTION_TYPES = [
    {"type": "run", "label": "เปิดโปรแกรม", "fields": [
        {"name": "program", "kind": "program", "required": True}]},
    {"type": "open", "label": "เปิดไฟล์/โฟลเดอร์", "fields": [
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


def unknown_programs(preset, programs):
    """(field, message) for each `run` step that names a program that is not in programs.json."""
    return [
        (f"actions.{i}.program", "unknown program")
        for i, action in enumerate(preset.actions)
        if action.type == "run" and action.program not in programs
    ]


def open_problems(preset):
    """(field, message) for each `open` step that is missing or not allowed from the web.

    Allowed: a folder, or a file of a type in OPEN_SUFFIXES. The path is judged after symlinks and
    short names are resolved and trailing dots/spaces dropped (Windows ignores them), so a link called
    a.pdf that points at a program does not get through. Messages never echo the path."""
    problems = []
    for i, action in enumerate(preset.actions):
        if action.type != "open":
            continue
        field = f"actions.{i}.target"
        expanded = os.path.expandvars(action.target).rstrip(" .")
        if not os.path.exists(expanded):
            problems.append((field, "path not found"))
            continue
        real = os.path.realpath(expanded)
        if not os.path.isdir(real) and PureWindowsPath(real).suffix.lower() not in OPEN_SUFFIXES:
            problems.append((field, OPEN_NOT_ALLOWED))
    return problems
