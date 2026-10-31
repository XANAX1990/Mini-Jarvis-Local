import json
from pathlib import Path

import pytest

from jarvis.settings import Settings, load_settings, parse_settings, validate_hotkey


@pytest.mark.parametrize("key", ["caps lock", "f9", "right ctrl", "pause", "ctrl+alt+j", "ctrl+a"])
def test_allowed_hotkeys(key):
    assert validate_hotkey(key) == (key, None)


def test_hotkey_is_normalized():
    assert validate_hotkey("  Ctrl + Alt+J ") == ("ctrl+alt+j", None)


@pytest.mark.parametrize(
    "key", ["a", "Z", "5", "space", "enter", "tab", "backspace", "esc", "left shift", "right shift", ";", "/"]
)
def test_typing_keys_are_refused_on_their_own(key):
    hotkey, reason = validate_hotkey(key)
    assert hotkey is None and "typing key" in reason


@pytest.mark.parametrize("key", ["", "+", "ctrl+", "ctrl+alt", "j+k", "a+b+c+d+e", "x" * 21, None, 5])
def test_malformed_hotkeys_are_refused(key):
    assert validate_hotkey(key)[0] is None


def test_defaults():
    s = Settings()
    assert (s.hotkey, s.armed_on_start, s.silence_ms, s.max_seconds, s.beep) == ("caps lock", True, 1000, 15, True)


def test_missing_file_gives_defaults(tmp_path):
    assert load_settings(tmp_path / "settings.json") == Settings()


def test_valid_file_is_loaded(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"hotkey": "right ctrl", "silence_ms": 800, "beep": False}), encoding="utf-8")
    s = load_settings(p)
    assert (s.hotkey, s.silence_ms, s.beep, s.max_seconds) == ("right ctrl", 800, False, 15)


def test_invalid_values_fall_back_one_by_one_with_a_log_line():
    lines = []
    s = parse_settings(
        {"hotkey": "a", "silence_ms": 10, "beep": "yes", "match_threshold": 10, "max_seconds": 20, "bogus": 1},
        log=lines.append,
    )
    assert s == Settings(max_seconds=20)
    assert len(lines) == 5
    assert any("hotkey" in line for line in lines) and any("bogus" in line for line in lines)


def test_booleans_are_not_numbers():
    assert parse_settings({"silence_ms": True}, log=lambda _: None).silence_ms == 1000


@pytest.mark.parametrize("text", ["{not json", "[1, 2]", ""])
def test_unreadable_file_gives_defaults_and_a_log_line(tmp_path, text):
    p = tmp_path / "settings.json"
    p.write_text(text, encoding="utf-8")
    lines = []
    assert load_settings(p, log=lines.append) == Settings()
    assert lines


def test_example_file_matches_the_defaults():
    example = json.loads((Path(__file__).resolve().parent.parent / "settings.example.json").read_text("utf-8"))
    assert parse_settings(example) == Settings()
    assert example == Settings().to_dict()
