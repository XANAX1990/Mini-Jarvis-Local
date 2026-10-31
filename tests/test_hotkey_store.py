import json
import threading
import time
from types import SimpleNamespace

import pytest

from jarvis import hotkey, log as jarvis_log
from jarvis.settings import Settings, load_settings, save_settings
from jarvis.store import PresetStore


class FakeKeyboard:
    """Just enough of the `keyboard` library; remembers hooks so a test can check they are removed."""

    def __init__(self, keys=()):
        self.hooks = []
        self.unhooked = []
        self.script = keys  # (event_type, name) pairs delivered once a hook exists

    def hook(self, callback):
        self.hooks.append(callback)
        threading.Thread(target=self._play, args=(callback,), daemon=True).start()
        return callback

    def _play(self, callback):
        for kind, name in self.script:
            time.sleep(0.01)
            callback(SimpleNamespace(event_type=kind, name=name))

    def unhook(self, handle):
        self.unhooked.append(handle)

    def get_hotkey_name(self, names):
        return "+".join(names)

    def parse_hotkey(self, key):
        if "nonsense" in key:
            raise ValueError("unknown key")

    def add_hotkey(self, key, callback, suppress=False):
        self.registered = (key, suppress)
        return "handle"

    def remove_hotkey(self, handle):
        self.registered = None


def test_capture_returns_the_first_combo_and_removes_its_hook():
    kb = FakeKeyboard([("down", "ctrl"), ("down", "alt"), ("down", "j"), ("up", "j"), ("down", "x"), ("up", "x")])
    assert hotkey.capture(2, keyboard=kb) == "ctrl+alt+j"
    assert kb.unhooked == kb.hooks and len(kb.hooks) == 1


def test_capture_times_out_and_still_removes_its_hook():
    kb = FakeKeyboard([])
    assert hotkey.capture(0.05, keyboard=kb) is None
    assert kb.unhooked == kb.hooks


def test_capture_ignores_a_release_before_any_press():
    kb = FakeKeyboard([("up", "enter"), ("down", "right ctrl"), ("up", "right ctrl")])
    assert hotkey.capture(2, keyboard=kb) == "right ctrl"


def test_check_reports_unknown_keys_without_echoing_them():
    kb = FakeKeyboard()
    assert hotkey.check("caps lock", kb) is None
    reason = hotkey.check("ctrl+nonsense", kb)
    assert reason and "nonsense" not in reason


def test_only_one_hotkey_is_registered_and_it_is_suppressed():
    kb = FakeKeyboard()
    hk = hotkey.Hotkeys(kb)
    hk.apply("caps lock", lambda: None)
    assert kb.registered == ("caps lock", True)
    hk.apply(None, lambda: None)
    assert kb.registered is None


# ---- store ----

PRESETS = {"game": {"phrases": ["เปิดโหมดเกม"], "reply": "ok", "actions": []}}


def test_save_writes_json_and_keeps_the_previous_file_as_bak(tmp_path):
    path = tmp_path / "presets.json"
    path.write_text(json.dumps({"old": 1}), encoding="utf-8")
    PresetStore(path).save(PRESETS)
    assert json.loads(path.read_text("utf-8")) == PRESETS
    assert json.loads((tmp_path / "presets.json.bak").read_text("utf-8")) == {"old": 1}
    assert not (tmp_path / "presets.json.tmp").exists()


def test_a_failed_replace_leaves_the_file_untouched_and_no_tmp(tmp_path, monkeypatch):
    path = tmp_path / "presets.json"
    path.write_text(json.dumps({"old": 1}), encoding="utf-8")
    before = path.read_bytes()

    def boom(*a):
        raise PermissionError("locked")

    monkeypatch.setattr("jarvis.store.os.replace", boom)
    with pytest.raises(PermissionError):
        PresetStore(path).save(PRESETS)
    assert path.read_bytes() == before
    assert not (tmp_path / "presets.json.tmp").exists()


def test_first_save_without_an_existing_file_has_no_bak(tmp_path):
    PresetStore(tmp_path / "presets.json").save(PRESETS)
    assert not (tmp_path / "presets.json.bak").exists()


# ---- settings save ----

def test_save_settings_roundtrip_is_atomic(tmp_path):
    path = tmp_path / "settings.json"
    new = Settings(hotkey="right ctrl", beep=False, match_threshold=80.0)
    save_settings(new, path)
    assert load_settings(path) == new
    assert not (tmp_path / "settings.json.tmp").exists()


# ---- log readers ----

def test_read_day_skips_garbage_lines_and_refuses_path_tricks(tmp_path):
    (tmp_path / "2026-10-31.jsonl").write_text('{"id": "a"}\nnot json\n[1, 2]\n\n{"id": "b"}\n', encoding="utf-8")
    assert [e["id"] for e in jarvis_log.read_day("2026-10-31", tmp_path)] == ["a", "b"]
    assert jarvis_log.read_day("2020-01-01", tmp_path) == []
    for bad in ("../x", "2026-10-31.jsonl", "..\\2026-10-31"):
        with pytest.raises(ValueError):
            jarvis_log.read_day(bad, tmp_path)


def test_list_days_newest_first_and_only_day_files(tmp_path):
    for name in ("2026-10-29.jsonl", "2026-10-31.jsonl", "commands.jsonl", "notes.txt"):
        (tmp_path / name).write_text("", encoding="utf-8")
    assert jarvis_log.list_days(tmp_path) == ["2026-10-31", "2026-10-29"]
    assert jarvis_log.list_days(tmp_path / "missing") == []


def test_find_entry_looks_through_all_days(tmp_path):
    (tmp_path / "2026-10-29.jsonl").write_text('{"id": "old", "transcript": "x"}\n', encoding="utf-8")
    assert jarvis_log.find_entry("old", tmp_path)["transcript"] == "x"
    assert jarvis_log.find_entry("nope", tmp_path) is None
