import json
import os

import pytest

from jarvis import programs as P
from jarvis.presets import EXAMPLE_PATH as PRESETS_EXAMPLE
from jarvis.presets import load_presets
from jarvis.programs import (
    EXAMPLE_PATH,
    Migration,
    ProgramError,
    ProgramStore,
    describe,
    ensure_programs_file,
    load_programs,
    migrate_legacy_steps,
    program_name,
    uri_name,
    validate_programs,
)

DISCORD_OLD = {"path": "%LocalAppData%\\Discord\\Update.exe", "args": ["--processStart", "Discord.exe"]}
DISCORD = {"kind": "exe", **DISCORD_OLD}
IDE_OLD = {"path": "%LocalAppData%\\Programs\\Antigravity\\Antigravity IDE.exe", "args": []}
IDE = {"kind": "exe", **IDE_OLD}
ROBLOX = {"kind": "uri", "uri": "roblox:"}


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


# ---- validation ----

def test_both_kinds_are_valid_and_returned_as_plain_dicts():
    out = validate_programs({"discord": DISCORD, "roblox": ROBLOX, "notepad": {"kind": "exe", "path": "C:\\Windows\\notepad.exe"}})
    assert out["discord"] == DISCORD and out["roblox"] == ROBLOX
    assert out["notepad"] == {"kind": "exe", "path": "C:\\Windows\\notepad.exe", "args": []}


def test_an_entry_from_before_kind_existed_is_an_exe():
    assert validate_programs({"discord": DISCORD_OLD})["discord"] == DISCORD


def test_an_empty_file_is_valid():
    assert validate_programs({}) == {}


def test_quotes_from_copy_as_path_are_stripped():
    assert validate_programs({"a": {"kind": "exe", "path": '"C:\\x\\a.exe"'}})["a"]["path"] == "C:\\x\\a.exe"


@pytest.mark.parametrize("data", [
    [], "x", {"A": DISCORD}, {"has space": DISCORD}, {"": DISCORD}, {"x" * 33: DISCORD},
    {"a": {"kind": "exe", "path": "a.exe"}}, {"a": {"kind": "exe", "path": "C:\\x\\a.bat"}},
    {"a": {"kind": "exe", "path": "C:\\x\\a.exe", "args": "x"}}, {"a": {"kind": "exe", "path": "C:\\x\\a.exe", "args": ["x"] * 21}},
    {"a": {"kind": "exe", "path": "C:\\x\\a.exe", "args": ["x" * 501]}}, {"a": {"kind": "exe", "path": "C:\\x\\a.exe", "extra": 1}},
    {"a": {"kind": "exe"}}, {"a": "C:\\x\\a.exe"}, {"a": {"kind": "bat", "path": "C:\\x\\a.exe"}},
    {"a": {"kind": "exe", "uri": "roblox:"}}, {"a": {"kind": "uri", "path": "C:\\x\\a.exe"}}, {"a": {"kind": "uri"}},
    {"a": {"kind": "uri", "uri": "file:///C:/x"}}, {"a": {"kind": "uri", "uri": "ms-settings:"}},
    {"a": {"kind": "uri", "uri": "ms-msdt:x"}}, {"a": {"kind": "uri", "uri": "javascript:alert(1)"}},
    {"a": {"kind": "uri", "uri": "C:\\x\\a.exe"}}, {"a": {"kind": "uri", "uri": "no scheme"}},
    {"a": {"kind": "uri", "uri": "roblox:", "args": []}}, {"a": {"kind": "uri", "uri": "x" * 501}},
])
def test_invalid_programs_are_refused_with_a_clear_error(data):
    with pytest.raises(ProgramError):
        validate_programs(data)


def test_the_error_names_the_entry_and_the_field():
    with pytest.raises(ProgramError, match=r"programs\.json: a\.path: must be an absolute path"):
        validate_programs({"a": {"kind": "exe", "path": "a.exe"}})
    with pytest.raises(ProgramError, match=r"a\.uri: the 'file:' scheme is not allowed"):
        validate_programs({"a": {"kind": "uri", "uri": "file:///x"}})


def test_load_programs(tmp_path):
    assert load_programs(tmp_path / "none.json") == {}  # no file yet: nothing is allowed
    f = tmp_path / "programs.json"
    f.write_text("{not json", encoding="utf-8")
    with pytest.raises(ProgramError, match="not valid JSON"):
        load_programs(f)
    write(f, {"discord": DISCORD_OLD, "roblox": ROBLOX})
    loaded = load_programs(f)
    assert loaded["discord"]["args"] == ["--processStart", "Discord.exe"] and loaded["roblox"]["uri"] == "roblox:"


def test_the_shipped_examples_work_together():
    programs = load_programs(EXAMPLE_PATH)
    presets = load_presets(PRESETS_EXAMPLE, programs=programs)
    assert {"discord", "notepad"} <= set(programs) and {p["kind"] for p in programs.values()} == {"exe", "uri"}
    assert presets["game"]["actions"][0] == {"type": "app", "name": "discord"}


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
    view = describe({"kind": "exe", "path": "%JARVIS_TEST_DIR%\\a.exe", "args": ["-x", "y z"]})
    assert view == {"kind": "exe", "path": os.path.realpath(exe), "args": ["-x", "y z"]}
    assert describe({"kind": "exe", "path": "C:\\no\\where.exe", "args": []}) == {"kind": "exe", "path": "C:\\no\\where.exe", "args": []}
    assert describe(ROBLOX) == ROBLOX  # a link is shown in full


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


@pytest.mark.parametrize("uri, expected", [("roblox:", "roblox"), ("steam://run/1", "steam"), ("Discord:", "discord"), ("calculator:", "calculator")])
def test_link_names_come_from_the_scheme(uri, expected):
    assert uri_name(uri, set()) == expected


def test_names_are_unique_and_always_valid():
    taken = set()
    for _ in range(12):
        taken.add(program_name("C:\\apps\\" + "long-name-" * 6 + ".exe", taken))
    assert len(taken) == 12 and all(len(n) <= 32 for n in taken)
    assert all(validate_programs({n: {"kind": "exe", "path": "C:\\a.exe"}}) for n in taken)
    assert uri_name("roblox:", {"roblox"}) == "roblox-2"


# ---- the one-time migration of older steps ----

def old_presets():
    return {
        "game": {"phrases": ["เปิดโหมดเกม"], "reply": "x", "actions": [
            {"type": "run", **DISCORD_OLD}, {"type": "uri", "target": "roblox:"}, {"type": "wait", "seconds": 3},
            {"type": "chrome", "urls": ["https://example.com"]}]},
        "work": {"phrases": ["เปิดโหมดทำงาน"], "reply": "x", "actions": [
            {"type": "run", **DISCORD_OLD}, {"type": "run", **IDE_OLD}, {"type": "uri", "target": "roblox:"},
            {"type": "chrome", "urls": ["https://example.com"]}]},
        "open-notes": {"phrases": ["เปิดโน้ต"], "reply": "x", "actions": [{"type": "run", "path": "C:\\Windows\\notepad.exe"}]},
        "spending-today": {"phrases": ["วันนี้จ่ายไปเท่าไร"], "reply": "x", "actions": [{"type": "spending", "period": "today"}]},
    }


def test_migration_turns_run_and_uri_steps_into_app_steps(tmp_path):
    pf, gf = tmp_path / "presets.json", tmp_path / "programs.json"
    original = old_presets()
    write(pf, original)
    result = migrate_legacy_steps(pf, gf)
    assert result.created == ["discord-update", "roblox", "antigravity-ide", "notepad"] and result.steps == 6
    assert read(gf) == {
        "discord-update": DISCORD,
        "roblox": ROBLOX,
        "antigravity-ide": IDE,
        "notepad": {"kind": "exe", "path": "C:\\Windows\\notepad.exe", "args": []},
    }
    moved = read(pf)
    assert [a for a in moved["game"]["actions"][:2]] == [{"type": "app", "name": "discord-update"}, {"type": "app", "name": "roblox"}]
    assert moved["work"]["actions"][:3] == [
        {"type": "app", "name": "discord-update"}, {"type": "app", "name": "antigravity-ide"}, {"type": "app", "name": "roblox"}]
    assert moved["open-notes"]["actions"] == [{"type": "app", "name": "notepad"}]
    for name in ("game", "work"):  # everything else is untouched
        assert moved[name]["actions"][-1] == original[name]["actions"][-1]
    assert moved["spending-today"] == original["spending-today"]
    assert read(tmp_path / "presets.json.bak") == original  # the old file is kept
    assert set(load_presets(pf, programs=load_programs(gf))) == set(original)  # and the result loads


def test_the_first_programs_json_shape_becomes_app_steps_and_gets_a_kind(tmp_path):
    """What the owner's files looked like before `app` existed: {"type": "run", "program"} and entries without kind."""
    pf, gf = tmp_path / "presets.json", tmp_path / "programs.json"
    write(gf, {"discord": DISCORD_OLD, "notepad": {"path": "C:\\Windows\\notepad.exe", "args": []}})
    write(pf, {"game": {"phrases": ["ก"], "reply": "", "actions": [
        {"type": "run", "program": "discord"}, {"type": "wait", "seconds": 1}, {"type": "run", "program": "notepad"}]}})
    result = migrate_legacy_steps(pf, gf)
    assert result.created == [] and result.steps == 2 and result
    assert read(pf)["game"]["actions"] == [{"type": "app", "name": "discord"}, {"type": "wait", "seconds": 1}, {"type": "app", "name": "notepad"}]
    assert read(gf)["discord"] == DISCORD and read(gf)["notepad"]["kind"] == "exe"  # normalized
    assert set(load_presets(pf, programs=load_programs(gf)))


def test_migration_is_idempotent(tmp_path):
    pf, gf = tmp_path / "presets.json", tmp_path / "programs.json"
    write(pf, old_presets())
    migrate_legacy_steps(pf, gf)
    before = (pf.read_bytes(), gf.read_bytes())
    again = migrate_legacy_steps(pf, gf)
    assert not again and again.created == [] and again.steps == 0
    assert (pf.read_bytes(), gf.read_bytes()) == before


def test_the_same_command_or_link_is_one_entry_and_different_args_are_another(tmp_path):
    pf, gf = tmp_path / "presets.json", tmp_path / "programs.json"
    write(pf, {"p": {"phrases": ["ก"], "reply": "", "actions": [
        {"type": "run", "path": "C:\\a\\tool.exe", "args": ["-x"]},
        {"type": "run", "path": "C:\\a\\tool.exe", "args": ["-x"]},
        {"type": "run", "path": "C:\\a\\tool.exe", "args": ["-y"]},
        {"type": "uri", "target": "roblox:"}, {"type": "uri", "target": "roblox:"}, {"type": "uri", "target": "roblox:play"}]}})
    assert migrate_legacy_steps(pf, gf).created == ["tool", "tool-2", "roblox", "roblox-2"]
    assert [a["name"] for a in read(pf)["p"]["actions"]] == ["tool", "tool", "tool-2", "roblox", "roblox", "roblox-2"]


def test_a_link_and_a_program_with_the_same_name_get_different_names(tmp_path):
    pf, gf = tmp_path / "presets.json", tmp_path / "programs.json"
    write(gf, {"discord": DISCORD})
    write(pf, {"p": {"phrases": ["ก"], "reply": "", "actions": [{"type": "uri", "target": "discord:"}]}})
    assert migrate_legacy_steps(pf, gf).created == ["discord-2"]
    assert read(gf)["discord"] == DISCORD and read(gf)["discord-2"] == {"kind": "uri", "uri": "discord:"}


def test_an_existing_entry_with_the_same_command_is_reused(tmp_path):
    pf, gf = tmp_path / "presets.json", tmp_path / "programs.json"
    write(gf, {"my-discord": DISCORD, "my-roblox": ROBLOX, "other": {"kind": "exe", "path": "C:\\o.exe", "args": []}})
    write(pf, {"game": {"phrases": ["ก"], "reply": "", "actions": [{"type": "run", **DISCORD_OLD}, {"type": "uri", "target": "roblox:"}]}})
    result = migrate_legacy_steps(pf, gf)
    assert result.created == [] and result.steps == 2
    assert read(pf)["game"]["actions"] == [{"type": "app", "name": "my-discord"}, {"type": "app", "name": "my-roblox"}]
    assert set(read(gf)) == {"my-discord", "my-roblox", "other"}


@pytest.mark.parametrize("target", ["file:///C:/Windows/notepad.exe", "ms-settings:", "javascript:alert(1)", "C:\\x\\a.exe", "no scheme"])
def test_a_link_the_rules_refuse_is_left_alone_so_loading_can_say_why(tmp_path, target):
    pf, gf = tmp_path / "presets.json", tmp_path / "programs.json"
    write(pf, {"p": {"phrases": ["ก"], "reply": "", "actions": [{"type": "uri", "target": target}]}})
    before = pf.read_bytes()
    result = migrate_legacy_steps(pf, gf)
    assert not result and pf.read_bytes() == before and not gf.exists()


def test_with_nothing_to_move_nothing_is_touched(tmp_path):
    pf, gf = tmp_path / "presets.json", tmp_path / "programs.json"
    write(pf, {"p": {"phrases": ["ก"], "reply": "", "actions": [{"type": "app", "name": "x"}, {"type": "wait", "seconds": 1}]}})
    before = pf.read_bytes()
    assert not migrate_legacy_steps(pf, gf)
    assert pf.read_bytes() == before and not gf.exists() and not (tmp_path / "presets.json.bak").exists()


@pytest.mark.parametrize("content", [None, "{not json", "[1, 2]", "{}"])
def test_a_missing_or_broken_presets_file_is_left_for_load_presets_to_report(tmp_path, content):
    pf = tmp_path / "presets.json"
    if content is not None:
        pf.write_text(content, encoding="utf-8")
    assert not migrate_legacy_steps(pf, tmp_path / "programs.json")
    assert not (tmp_path / "programs.json").exists()


def test_a_broken_programs_file_stops_the_migration_before_anything_is_written(tmp_path):
    pf, gf = tmp_path / "presets.json", tmp_path / "programs.json"
    write(pf, old_presets())
    gf.write_text("{not json", encoding="utf-8")
    before = pf.read_bytes()
    with pytest.raises(ProgramError):
        migrate_legacy_steps(pf, gf)
    assert pf.read_bytes() == before and gf.read_text(encoding="utf-8") == "{not json"


def test_an_interrupted_migration_is_finished_by_the_next_start(tmp_path, monkeypatch):
    pf, gf = tmp_path / "presets.json", tmp_path / "programs.json"
    write(pf, old_presets())
    real = P._write_atomic
    calls = []

    def flaky(path, data, keep_backup):
        calls.append(path.name)
        if path.name == "presets.json":
            raise OSError("power cut")
        real(path, data, keep_backup)

    monkeypatch.setattr(P, "_write_atomic", flaky)
    with pytest.raises(OSError):
        migrate_legacy_steps(pf, gf)
    assert calls == ["programs.json", "presets.json"]  # programs first, so nothing is lost
    assert read(pf)["game"]["actions"][0]["type"] == "run"  # presets still the old file
    monkeypatch.setattr(P, "_write_atomic", real)
    migrate_legacy_steps(pf, gf)  # the next start
    assert read(pf)["game"]["actions"][0] == {"type": "app", "name": "discord-update"}
    assert set(load_presets(pf, programs=load_programs(gf)))


def test_steps_that_are_not_old_run_or_uri_steps_never_invent_programs(tmp_path):
    pf, gf = tmp_path / "presets.json", tmp_path / "programs.json"
    write(pf, {"p": {"phrases": ["ก"], "reply": "", "actions": [
        {"type": "open", "target": "C:\\x\\a.pdf"}, {"type": "run", "path": 5}, {"type": "uri", "target": 5}, "not a dict"]}})
    assert not migrate_legacy_steps(pf, gf) and not gf.exists()


def test_the_migration_result_is_falsy_when_nothing_changed():
    assert not Migration() and Migration(created=[], steps=1) and Migration(created=["a"], steps=0).created == ["a"]
