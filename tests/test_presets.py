import copy
import re

import pytest

from jarvis.presets import PresetError, get_preset, load_presets, validate_presets

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


def test_shipped_presets_json_is_valid():
    presets = load_presets()
    assert {"game", "work"} <= set(presets)


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
