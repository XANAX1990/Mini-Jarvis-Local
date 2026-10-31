import copy
import re

import pytest

from jarvis import __main__ as app
from jarvis.presets import EXAMPLE_PATH, PresetError, ensure_presets_file, get_preset, load_presets, validate_presets

VALID = {
    "game": {
        "phrases": ["เปิดโหมดเกม"],
        "reply": "ok",
        "actions": [
            {"type": "run", "program": "tool"},
            {"type": "open", "target": "C:\\file.lnk"},
            {"type": "uri", "target": "roblox:"},
            {"type": "chrome", "urls": ["https://example.com"]},
            {"type": "wait", "seconds": 1.5},
        ],
    }
}


def broken(mutate):
    data = copy.deepcopy(VALID)
    mutate(data["game"])
    return data


def test_valid_presets_pass():
    assert validate_presets(copy.deepcopy(VALID)) == VALID


def test_shipped_example_presets_are_valid():
    presets = load_presets(EXAMPLE_PATH)  # presets.json is the owner's and git-ignored: the example is what ships
    assert {"game", "work", "spending-today", "spending-week", "spending-month"} <= set(presets)


def test_first_run_copies_the_example_and_never_overwrites(tmp_path):
    mine = tmp_path / "presets.json"
    assert ensure_presets_file(mine, EXAMPLE_PATH) is True
    assert mine.read_bytes() == EXAMPLE_PATH.read_bytes()
    mine.write_text("{}", encoding="utf-8")  # the owner edits it
    assert ensure_presets_file(mine, EXAMPLE_PATH) is False
    assert mine.read_text(encoding="utf-8") == "{}"


def test_first_run_without_an_example_leaves_the_clear_error_to_load_presets(tmp_path):
    mine = tmp_path / "presets.json"
    assert ensure_presets_file(mine, tmp_path / "nope.json") is False
    assert not mine.exists()
    with pytest.raises(PresetError, match="not found"):
        load_presets(mine)


def test_presets_json_is_git_ignored_and_the_example_is_not():
    from pathlib import Path

    lines = (Path(__file__).resolve().parent.parent / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "presets.json" in lines and "presets.example.json" not in lines


def test_first_run_tells_the_owner_that_the_files_were_created(quiet_main, monkeypatch, capsys):
    monkeypatch.setattr(app, "ensure_presets_file", lambda: True)
    monkeypatch.setattr(app, "ensure_programs_file", lambda: True)
    assert app.main(["list"]) == 0
    out = capsys.readouterr().out
    assert "created presets.json from presets.example.json" in out
    assert "created programs.json from programs.example.json" in out


def test_a_start_that_moved_programs_says_which(quiet_main, monkeypatch, capsys):
    monkeypatch.setattr(app, "migrate_legacy_runs", lambda *a, **k: ["discord-update", "notepad"])
    assert app.main(["list"]) == 0
    out = capsys.readouterr().out
    assert "discord-update, notepad" in out and "presets.json.bak" in out


TOOLS = {"tool": {"path": "C:\\tools\\a.exe", "args": ["--x"]}}


def test_a_run_step_must_name_a_program_that_exists():
    assert validate_presets(copy.deepcopy(VALID), TOOLS)["game"]["actions"][0] == {"type": "run", "program": "tool"}
    with pytest.raises(PresetError, match="preset 'game' action 1: program 'tool' is not in programs.json"):
        validate_presets(copy.deepcopy(VALID), {})
    validate_presets(copy.deepcopy(VALID))  # without programs there is nothing to check against


def test_load_presets_checks_the_programs_too(tmp_path):
    import json

    f = tmp_path / "presets.json"
    f.write_text(json.dumps(VALID), encoding="utf-8")
    assert "game" in load_presets(f, programs=TOOLS)
    with pytest.raises(PresetError, match="not in programs.json"):
        load_presets(f, programs={})


def test_a_run_step_starts_the_program_from_programs_json(monkeypatch):
    from jarvis import presets

    started = []
    monkeypatch.setattr(presets.subprocess, "Popen", lambda argv: started.append(argv))
    monkeypatch.setenv("JARVIS_TEST_DIR", "C:\\x")
    programs = {"tool": {"path": "%JARVIS_TEST_DIR%\\a.exe", "args": ["--x", "%JARVIS_TEST_DIR%"]}}
    presets.run_action({"type": "run", "program": "tool"}, programs)
    assert started == [["C:\\x\\a.exe", "--x", "C:\\x"]]  # a list: never joined into a command line


def test_a_run_step_never_starts_anything_programs_json_does_not_name(monkeypatch):
    from jarvis import presets

    started = []
    monkeypatch.setattr(presets.subprocess, "Popen", lambda argv: started.append(argv))
    for action in (
        {"type": "run", "program": "nope"},
        {"type": "run", "path": "C:\\Windows\\System32\\calc.exe"},  # the old shape: no longer runs
        {"type": "run"},
    ):
        with pytest.raises(OSError):
            presets.run_action(action, {"tool": {"path": "C:\\a.exe", "args": []}})
        with pytest.raises(OSError):
            presets.run_action(action, None)
    assert started == []


def test_a_failing_run_step_is_reported_and_the_rest_still_run(monkeypatch):
    from jarvis import presets

    ran = []
    monkeypatch.setattr(presets.subprocess, "Popen", lambda argv: ran.append(argv))
    data = {"p": {"phrases": ["ก"], "reply": "", "actions": [
        {"type": "run", "program": "gone"}, {"type": "run", "program": "tool"}]}}
    log = []
    assert presets.run_preset(data, "p", log.append, programs=TOOLS) == 1
    assert ran == [["C:\\tools\\a.exe", "--x"]] and "gone" in log[0]


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda p: p["actions"].append({"type": "format_disk"}), "does not match any of the expected tags"),
        (lambda p: p["actions"].append({"type": "run"}), "actions[6].program: Field required"),
        (lambda p: p["actions"].append({"type": "uri"}), "actions[6].target: Field required"),
        (lambda p: p["actions"].append({"type": "chrome", "urls": []}), "at least 1 item"),
        (lambda p: p["actions"].append({"type": "wait", "seconds": -1}), "greater than or equal to 0"),
        (lambda p: p["actions"].append({"type": "wait", "seconds": True}), "valid integer"),
        (lambda p: p["actions"].append({"type": "run", "program": "tool", "path": "C:\\a.exe"}), "actions[6].path: Extra inputs are not permitted"),
        (lambda p: p["actions"].append({"type": "run", "path": "C:\\a.exe", "args": "x"}), "actions[6].program: Field required"),
        (lambda p: p["actions"].append({"type": "run", "program": "Tool"}), "actions[6].program"),
        (lambda p: p.pop("phrases"), "phrases"),
        (lambda p: p.update(phrases=[]), "phrases"),
        (lambda p: p.pop("reply"), "reply"),
        (lambda p: p.update(actions="nope"), "actions"),
    ],
)
def test_invalid_presets_raise_clear_error(mutate, message):
    with pytest.raises(PresetError, match=re.escape(message)):
        validate_presets(broken(mutate))


def test_empty_or_non_object_rejected():
    with pytest.raises(PresetError):
        validate_presets({})
    with pytest.raises(PresetError):
        validate_presets([])


def test_unknown_preset_name():
    with pytest.raises(PresetError, match="unknown preset 'nope'"):
        get_preset(VALID, "nope")


def test_missing_file_is_clear_error(tmp_path):
    with pytest.raises(PresetError, match="not found"):
        load_presets(tmp_path / "missing.json")


def test_bad_json_is_clear_error(tmp_path):
    bad = tmp_path / "p.json"
    bad.write_text("{oops", encoding="utf-8")
    with pytest.raises(PresetError, match="not valid JSON"):
        load_presets(bad)
