import json
import os

import pytest

from jarvis import programs as P
from jarvis.presets import EXAMPLE_PATH as PRESETS_EXAMPLE
from jarvis.presets import load_presets
from jarvis.programs import (
    EXAMPLE_PATH,
    ProgramError,
    ProgramStore,
    describe,
    ensure_programs_file,
    load_programs,
    migrate_legacy_runs,
    program_name,
    validate_programs,
)

DISCORD = {"path": "%LocalAppData%\\Discord\\Update.exe", "args": ["--processStart", "Discord.exe"]}
IDE = {"path": "%LocalAppData%\\Programs\\Antigravity\\Antigravity IDE.exe", "args": []}


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


# ---- validation ----

def test_valid_programs_are_returned_as_plain_dicts():
    out = validate_programs({"discord": DISCORD, "notepad": {"path": "C:\\Windows\\notepad.exe"}})
    assert out["discord"] == DISCORD and out["notepad"] == {"path": "C:\\Windows\\notepad.exe", "args": []}


def test_an_empty_file_is_valid():
    assert validate_programs({}) == {}


def test_quotes_from_copy_as_path_are_stripped():
    assert validate_programs({"a": {"path": '"C:\\x\\a.exe"'}})["a"]["path"] == "C:\\x\\a.exe"


@pytest.mark.parametrize("data", [
    [], "x", {"A": DISCORD}, {"has space": DISCORD}, {"": DISCORD}, {"x" * 33: DISCORD},
    {"a": {"path": "a.exe"}}, {"a": {"path": "C:\\x\\a.bat"}}, {"a": {"path": "C:\\x\\a.exe", "args": "x"}},
    {"a": {"path": "C:\\x\\a.exe", "args": ["x"] * 21}}, {"a": {"path": "C:\\x\\a.exe", "args": ["x" * 501]}},
    {"a": {"path": "C:\\x\\a.exe", "extra": 1}}, {"a": {"args": []}}, {"a": "C:\\x\\a.exe"},
])
def test_invalid_programs_are_refused_with_a_clear_error(data):
    with pytest.raises(ProgramError):
        validate_programs(data)


def test_load_programs(tmp_path):
    assert load_programs(tmp_path / "none.json") == {}  # no file yet: nothing is allowed
    f = tmp_path / "programs.json"
    f.write_text("{not json", encoding="utf-8")
    with pytest.raises(ProgramError, match="not valid JSON"):
        load_programs(f)
    write(f, {"discord": DISCORD})
    assert load_programs(f)["discord"]["args"] == ["--processStart", "Discord.exe"]


def test_the_shipped_examples_work_together():
    programs = load_programs(EXAMPLE_PATH)
    presets = load_presets(PRESETS_EXAMPLE, programs=programs)
    assert {"discord", "notepad"} <= set(programs)
    assert presets["game"]["actions"][0] == {"type": "run", "program": "discord"}


# ---- files ----

def test_first_run_copies_the_example_and_never_overwrites(tmp_path):
    mine = tmp_path / "programs.json"
    assert ensure_programs_file(mine, EXAMPLE_PATH) is True
    assert mine.read_bytes() == EXAMPLE_PATH.read_bytes()
    mine.write_text("{}", encoding="utf-8")
    assert ensure_programs_file(mine, EXAMPLE_PATH) is False
    assert mine.read_text(encoding="utf-8") == "{}"
    assert ensure_programs_file(tmp_path / "x.json", tmp_path / "no-example.json") is False


def test_store_saves_atomically_and_keeps_the_old_file(tmp_path):
    f = tmp_path / "programs.json"
    write(f, {"discord": DISCORD})
    store = ProgramStore(f)
    store.load()
    store.save({"discord": DISCORD, "ide": IDE})
    assert set(read(f)) == {"discord", "ide"} and set(store.programs) == {"discord", "ide"}
    assert set(read(tmp_path / "programs.json.bak")) == {"discord"}
    assert not (tmp_path / "programs.json.tmp").exists()


def test_a_failed_save_changes_nothing(tmp_path, monkeypatch):
    f = tmp_path / "programs.json"
    write(f, {"discord": DISCORD})
    store = ProgramStore(f)
    store.load()
    before = f.read_bytes()

    def boom(*a):
        raise PermissionError("locked")

    monkeypatch.setattr(P.os, "replace", boom)
    with pytest.raises(PermissionError):
        store.save({"ide": IDE})
    assert f.read_bytes() == before and not (tmp_path / "programs.json.tmp").exists()
    assert set(store.programs) == {"discord"}


def test_describe_shows_the_real_path_and_every_argument(monkeypatch, tmp_path):
    exe = tmp_path / "a.exe"
    exe.write_text("x", encoding="utf-8")
    monkeypatch.setenv("JARVIS_TEST_DIR", str(tmp_path))
    path, args = describe({"path": "%JARVIS_TEST_DIR%\\a.exe", "args": ["-x", "y z"]})
    assert path == os.path.realpath(exe) and args == ["-x", "y z"]
    assert describe({"path": "C:\\no\\where.exe", "args": []}) == ("C:\\no\\where.exe", [])


# ---- names ----

@pytest.mark.parametrize("path, expected", [
    ("C:\\Windows\\notepad.exe", "notepad"),
    ("C:\\Program Files\\Notepad++\\notepad++.exe", "notepad"),
    ("%LocalAppData%\\Discord\\Update.exe", "discord-update"),
    ("%LocalAppData%\\Programs\\Antigravity\\Antigravity IDE.exe", "antigravity-ide"),
    ("C:\\x\\!!!.exe", "program"),
])
def test_program_names_are_readable(path, expected):
    assert program_name(path, set()) == expected


def test_program_names_are_unique_and_always_valid():
    taken = set()
    for _ in range(12):
        taken.add(program_name("C:\\apps\\" + "long-name-" * 6 + ".exe", taken))
    assert len(taken) == 12
    assert all(validate_programs({n: {"path": "C:\\a.exe"}}) for n in taken) and all(len(n) <= 32 for n in taken)


# ---- the one-time migration of `run` steps that carry their own path and args ----

def legacy_presets():
    return {
        "game": {"phrases": ["เปิดโหมดเกม"], "reply": "x", "actions": [
            {"type": "run", **DISCORD}, {"type": "wait", "seconds": 3}, {"type": "chrome", "urls": ["https://example.com"]}]},
        "work": {"phrases": ["เปิดโหมดทำงาน"], "reply": "x", "actions": [
            {"type": "run", **DISCORD}, {"type": "run", **IDE}, {"type": "chrome", "urls": ["https://example.com"]}]},
        "open-notes": {"phrases": ["เปิดโน้ต"], "reply": "x", "actions": [{"type": "run", "path": "C:\\Windows\\notepad.exe"}]},
        "spending-today": {"phrases": ["วันนี้จ่ายไปเท่าไร"], "reply": "x", "actions": [{"type": "spending", "period": "today"}]},
    }


def test_migration_moves_run_steps_into_programs_json(tmp_path):
    pf, gf = tmp_path / "presets.json", tmp_path / "programs.json"
    original = legacy_presets()
    write(pf, original)
    created = migrate_legacy_runs(pf, gf)
    assert created == ["discord-update", "antigravity-ide", "notepad"]
    assert read(gf) == {
        "discord-update": DISCORD,
        "antigravity-ide": IDE,
        "notepad": {"path": "C:\\Windows\\notepad.exe", "args": []},
    }
    moved = read(pf)
    assert moved["game"]["actions"][0] == {"type": "run", "program": "discord-update"}
    assert moved["work"]["actions"][:2] == [
        {"type": "run", "program": "discord-update"}, {"type": "run", "program": "antigravity-ide"}]
    assert moved["open-notes"]["actions"] == [{"type": "run", "program": "notepad"}]
    for name in ("game", "work"):  # everything else is untouched
        assert moved[name]["actions"][-1] == original[name]["actions"][-1]
    assert moved["spending-today"] == original["spending-today"]
    assert read(tmp_path / "presets.json.bak") == original  # the old file is kept
    # and the result loads, with every program present
    assert set(load_presets(pf, programs=load_programs(gf))) == set(original)


def test_migration_is_idempotent(tmp_path):
    pf, gf = tmp_path / "presets.json", tmp_path / "programs.json"
    write(pf, legacy_presets())
    migrate_legacy_runs(pf, gf)
    before = (pf.read_bytes(), gf.read_bytes())
    assert migrate_legacy_runs(pf, gf) == []
    assert (pf.read_bytes(), gf.read_bytes()) == before


def test_the_same_command_is_one_program_and_different_args_are_another(tmp_path):
    pf, gf = tmp_path / "presets.json", tmp_path / "programs.json"
    data = {"p": {"phrases": ["ก"], "reply": "", "actions": [
        {"type": "run", "path": "C:\\a\\tool.exe", "args": ["-x"]},
        {"type": "run", "path": "C:\\a\\tool.exe", "args": ["-x"]},
        {"type": "run", "path": "C:\\a\\tool.exe", "args": ["-y"]}]}}
    write(pf, data)
    assert migrate_legacy_runs(pf, gf) == ["tool", "tool-2"]
    assert [a["program"] for a in read(pf)["p"]["actions"]] == ["tool", "tool", "tool-2"]


def test_an_existing_program_with_the_same_command_is_reused(tmp_path):
    pf, gf = tmp_path / "presets.json", tmp_path / "programs.json"
    write(gf, {"my-discord": DISCORD, "other": {"path": "C:\\o.exe", "args": []}})
    write(pf, {"game": {"phrases": ["ก"], "reply": "", "actions": [{"type": "run", **DISCORD}]}})
    assert migrate_legacy_runs(pf, gf) == []
    assert read(pf)["game"]["actions"] == [{"type": "run", "program": "my-discord"}]
    assert set(read(gf)) == {"my-discord", "other"}


def test_with_nothing_to_move_nothing_is_touched(tmp_path):
    pf, gf = tmp_path / "presets.json", tmp_path / "programs.json"
    write(pf, {"p": {"phrases": ["ก"], "reply": "", "actions": [{"type": "run", "program": "x"}, {"type": "wait", "seconds": 1}]}})
    before = pf.read_bytes()
    assert migrate_legacy_runs(pf, gf) == []
    assert pf.read_bytes() == before and not gf.exists() and not (tmp_path / "presets.json.bak").exists()


@pytest.mark.parametrize("content", [None, "{not json", "[1, 2]", "{}"])
def test_a_missing_or_broken_presets_file_is_left_for_load_presets_to_report(tmp_path, content):
    pf = tmp_path / "presets.json"
    if content is not None:
        pf.write_text(content, encoding="utf-8")
    assert migrate_legacy_runs(pf, tmp_path / "programs.json") == []
    assert not (tmp_path / "programs.json").exists()


def test_a_broken_programs_file_stops_the_migration_before_anything_is_written(tmp_path):
    pf, gf = tmp_path / "presets.json", tmp_path / "programs.json"
    write(pf, legacy_presets())
    gf.write_text("{not json", encoding="utf-8")
    before = pf.read_bytes()
    with pytest.raises(ProgramError):
        migrate_legacy_runs(pf, gf)
    assert pf.read_bytes() == before and gf.read_text(encoding="utf-8") == "{not json"


def test_an_interrupted_migration_is_finished_by_the_next_start(tmp_path, monkeypatch):
    pf, gf = tmp_path / "presets.json", tmp_path / "programs.json"
    write(pf, legacy_presets())
    real = P._write_atomic
    calls = []

    def flaky(path, data, keep_backup):
        calls.append(path.name)
        if path.name == "presets.json":
            raise OSError("power cut")
        real(path, data, keep_backup)

    monkeypatch.setattr(P, "_write_atomic", flaky)
    with pytest.raises(OSError):
        migrate_legacy_runs(pf, gf)
    assert calls == ["programs.json", "presets.json"]  # programs first, so nothing is lost
    assert "path" in read(pf)["game"]["actions"][0]  # presets still the old, valid file
    monkeypatch.setattr(P, "_write_atomic", real)
    migrate_legacy_runs(pf, gf)  # the next start
    assert read(pf)["game"]["actions"][0] == {"type": "run", "program": "discord-update"}
    assert set(load_presets(pf, programs=load_programs(gf)))  # consistent again


def test_programs_are_never_invented_from_a_step_that_is_not_a_legacy_run(tmp_path):
    pf, gf = tmp_path / "presets.json", tmp_path / "programs.json"
    write(pf, {"p": {"phrases": ["ก"], "reply": "", "actions": [
        {"type": "open", "target": "C:\\x\\a.pdf"}, {"type": "run", "path": 5}, "not a dict"]}})
    assert migrate_legacy_runs(pf, gf) == []
    assert not gf.exists()
