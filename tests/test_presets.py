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
            {"type": "run", "path": "C:\\tools\\a.exe", "args": ["--x"]},
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


def test_first_run_tells_the_owner_that_presets_json_was_created(monkeypatch, capsys):
    monkeypatch.setattr(app, "ensure_presets_file", lambda: True)
    monkeypatch.setattr(app, "load_presets", lambda: {"game": {"phrases": ["เปิดโหมดเกม"]}})
    assert app.main(["list"]) == 0
    assert "created presets.json from presets.example.json" in capsys.readouterr().out


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda p: p["actions"].append({"type": "format_disk"}), "does not match any of the expected tags"),
        (lambda p: p["actions"].append({"type": "run"}), "actions[6].path: Field required"),
        (lambda p: p["actions"].append({"type": "uri"}), "actions[6].target: Field required"),
        (lambda p: p["actions"].append({"type": "chrome", "urls": []}), "at least 1 item"),
        (lambda p: p["actions"].append({"type": "wait", "seconds": -1}), "greater than or equal to 0"),
        (lambda p: p["actions"].append({"type": "wait", "seconds": True}), "valid integer"),
        (lambda p: p["actions"].append({"type": "run", "path": "C:\\a.exe", "args": "x"}), "args: Input should be a valid list"),
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
