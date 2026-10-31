import json
import os
import socket
import sys
import threading
import urllib.request
from typing import get_args

import pytest
from fastapi.testclient import TestClient

from jarvis import log as jarvis_log
from jarvis.api import DEV_ORIGIN, MAX_BODY_BYTES, create_app
from jarvis.matcher import match
from jarvis.models import ACTION_TYPES, Action
from jarvis.presets import validate_presets
from jarvis.programs import ProgramStore
from jarvis.server import ApiServer, PortInUse, ensure_port_free
from jarvis.settings import Settings
from jarvis.store import PresetStore
from tests.test_engine import Rig

EXE = sys.executable  # an absolute path to an .exe that exists
H = {"X-Jarvis": "1", "Origin": "http://127.0.0.1:3003"}
BASE = "http://127.0.0.1:3003"

PRESETS = {
    "game": {"phrases": ["เปิดโหมดเกม"], "reply": "เปิดโหมดเกมแล้ว", "actions": [{"type": "wait", "seconds": 0}]},
    "work": {"phrases": ["เปิดโหมดงาน", "โหมดทำงาน"], "reply": "เปิดโหมดงานแล้ว", "actions": []},
}


class Env:
    def __init__(self, tmp_path, dev=False, capture=None, web_dir=None, confirm=None):
        self.dir = tmp_path
        self.presets_path = tmp_path / "presets.json"
        self.presets_path.write_text(json.dumps(PRESETS, ensure_ascii=False, indent=2), encoding="utf-8")
        self.logs = tmp_path / "logs"
        self.settings_path = tmp_path / "settings.json"
        self.rig = Rig(presets=validate_presets(json.loads(self.presets_path.read_text("utf-8"))))
        self.engine = self.rig.engine
        self.rig.log_command = lambda *a: jarvis_log.log_command(*a, directory=self.logs)
        self.engine._log_command = self.rig.log_command
        self.programs_path = tmp_path / "programs.json"
        self.programs_path.write_text(json.dumps({"tool": {"path": EXE, "args": []}}, indent=2), encoding="utf-8")
        self.program_store = ProgramStore(self.programs_path)
        self.program_store.load()
        self.asked = []  # what the confirmation box was asked: (name, path, args)
        self.answer = "yes"  # what the person "clicks"; set to "no" or "timeout"

        def person(name, path, args):
            self.asked.append((name, path, list(args)))
            return self.answer

        self.app = create_app(
            self.engine, PresetStore(self.presets_path), program_store=self.program_store,
            settings_path=self.settings_path, logs_dir=self.logs, dev=dev, capture=capture,
            confirm=confirm or person, web_dir=web_dir, log=lambda *_: None,
        )
        self.client = TestClient(self.app, base_url=BASE, raise_server_exceptions=False)

    def get(self, url, **kw):
        return self.client.get(url, **kw)

    def post(self, url, json=None, headers=H, **kw):
        return self.client.post(url, json={} if json is None else json, headers=headers, **kw)

    def put(self, url, json=None, headers=H):
        return self.client.put(url, json=json, headers=headers)

    def delete(self, url, headers=None):
        return self.client.delete(url, headers=headers or {**H, "Content-Type": "application/json"})

    def new_preset(self, **over):
        return {"phrases": ["เปิดโน้ต"], "reply": "ได้เลย", "actions": [{"type": "run", "program": "tool"}], **over}


@pytest.fixture
def env(tmp_path):
    e = Env(tmp_path)
    yield e
    e.engine.close()


# ---- security: Host, Origin, X-Jarvis, JSON ----

def test_wrong_host_is_forbidden_even_for_get(env):
    r = env.get("/api/state", headers={"Host": "evil.example:3003"})
    assert r.status_code == 403
    assert env.get("/api/state", headers={"Host": "127.0.0.1:9999"}).status_code == 403
    assert env.get("/api/state", headers={"Host": "127.0.0.1"}).status_code == 403


def test_both_loopback_names_are_accepted(env):
    assert env.get("/api/state", headers={"Host": "localhost:3003"}).status_code == 200


def test_post_without_x_jarvis_is_forbidden(env):
    r = env.post("/api/armed", {"armed": True}, headers={"Origin": "http://127.0.0.1:3003"})
    assert r.status_code == 403
    assert env.engine.armed is False


def test_post_with_a_foreign_origin_is_forbidden(env):
    for origin in ("https://evil.example", "http://127.0.0.1:3004", DEV_ORIGIN, "null"):
        r = env.post("/api/armed", {"armed": True}, headers={"X-Jarvis": "1", "Origin": origin})
        assert r.status_code == 403, origin
    assert env.engine.armed is False


def test_post_without_an_origin_is_forbidden(env):
    assert env.post("/api/armed", {"armed": True}, headers={"X-Jarvis": "1"}).status_code == 403


def test_non_json_content_type_is_forbidden(env):
    r = env.client.post("/api/armed", content='{"armed": true}', headers={**H, "Content-Type": "text/plain"})
    assert r.status_code == 403
    r = env.client.post("/api/armed", data={"armed": "true"}, headers=H)  # form encoded
    assert r.status_code == 403


def test_every_non_get_method_is_checked(env):
    assert env.client.put("/api/presets/game", json=env.new_preset()).status_code == 403
    assert env.client.delete("/api/presets/game").status_code == 403
    assert env.client.options("/api/state").status_code == 403
    assert env.presets_path.read_text("utf-8") == json.dumps(PRESETS, ensure_ascii=False, indent=2)


def test_an_oversized_body_is_refused(env):
    r = env.client.post("/api/armed", content=b"x" * (MAX_BODY_BYTES + 1), headers={**H, "Content-Type": "application/json"})
    assert r.status_code == 413


def test_security_headers_are_on_every_response(env):
    r = env.get("/api/state")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["cache-control"] == "no-store"
    assert "access-control-allow-origin" not in r.headers
    assert env.get("/api/state", headers={"Host": "evil:1"}).headers["x-content-type-options"] == "nosniff"


def test_no_cors_in_normal_mode(env):
    r = env.get("/api/state", headers={"Origin": DEV_ORIGIN})
    assert "access-control-allow-origin" not in r.headers
    pre = env.client.options("/api/armed", headers={"Origin": DEV_ORIGIN, "Access-Control-Request-Method": "POST"})
    assert pre.status_code == 403 and "access-control-allow-origin" not in pre.headers


def test_dev_mode_allows_only_the_dev_origin(tmp_path):
    e = Env(tmp_path, dev=True)
    pre = e.client.options("/api/armed", headers={
        "Origin": DEV_ORIGIN, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "x-jarvis,content-type"})
    assert pre.status_code == 200
    assert pre.headers["access-control-allow-origin"] == DEV_ORIGIN
    assert "access-control-allow-credentials" not in pre.headers
    foreign = e.client.options("/api/armed", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in foreign.headers
    ok = e.post("/api/armed", {"armed": True}, headers={"X-Jarvis": "1", "Origin": DEV_ORIGIN})
    assert ok.status_code == 200 and ok.headers["access-control-allow-origin"] == DEV_ORIGIN
    e.engine.close()


def test_the_dev_origin_is_refused_when_not_in_dev_mode(env):
    r = env.post("/api/armed", {"armed": True}, headers={"X-Jarvis": "1", "Origin": DEV_ORIGIN})
    assert r.status_code == 403


def test_unknown_body_fields_are_refused(env):
    r = env.post("/api/armed", {"armed": True, "extra": 1})
    assert r.status_code == 422
    assert env.post("/api/armed", {"armed": "yes"}).status_code == 422


def test_errors_are_short_and_leak_nothing(env):
    env.engine._presets = None  # make the next call blow up with an internal error
    r = env.get("/api/presets")
    assert r.status_code == 500 and r.json() == {"error": "internal"}
    bad = env.post("/api/armed", {"armed": {"x": "C:\\secret\\path"}})
    assert "secret" not in bad.text and "input" not in bad.json()["fields"][0]


# ---- state, switch, toggle ----

def test_state(env):
    body = env.get("/api/state").json()
    assert body == {"armed": False, "state": "off", "hotkey": "caps lock", "preset": None, "last": None}


def test_armed_switch_and_toggle(env):
    assert env.post("/api/armed", {"armed": True}).json()["state"] == "idle"
    assert env.rig.hotkeys.calls[-1] == "caps lock"
    r = env.post("/api/listen/toggle")
    assert r.status_code == 200 and r.json()["accepted"] is True
    assert env.engine.wait_idle()
    last = env.get("/api/state").json()["last"]
    assert (last["preset"], last["result"]) == ("game", "ok")  # the rig's fake mic and matcher hear "game"
    assert set(last) == {"time", "transcript", "preset", "score", "result"}
    assert env.post("/api/armed", {"armed": False}).json()["state"] == "off"
    assert env.rig.hotkeys.calls[-1] is None


def test_toggle_while_off_is_not_accepted(env):
    assert env.post("/api/listen/toggle").json()["accepted"] is False


# ---- presets ----

def test_list_presets(env):
    names = [p["name"] for p in env.get("/api/presets").json()["presets"]]
    assert names == ["game", "work"]


def test_action_types_cover_every_action_model(env):
    served = {t["type"] for t in env.get("/api/action-types").json()["types"]}
    union = get_args(Action)[0]
    models = {get_args(m.model_fields["type"].annotation)[0] for m in get_args(union)}
    assert served == models == {t["type"] for t in ACTION_TYPES}


def test_create_preset_is_saved_and_matched_without_a_restart(env):
    r = env.post("/api/presets", {"name": "notes", **env.new_preset()})
    assert r.status_code == 201 and r.json() == {"name": "notes", "warnings": []}
    saved = json.loads(env.presets_path.read_text("utf-8"))
    assert saved["notes"]["phrases"] == ["เปิดโน้ต"] and list(saved) == ["game", "work", "notes"]
    assert match("เปิดโน้ต", env.engine.presets)[0] == "notes"
    assert env.engine._prompt.endswith("เปิดโน้ต")
    assert (env.dir / "presets.json.bak").exists() and not (env.dir / "presets.json.tmp").exists()
    assert json.loads((env.dir / "presets.json.bak").read_text("utf-8")) == PRESETS


def test_create_with_an_existing_name_is_a_conflict(env):
    assert env.post("/api/presets", {"name": "game", **env.new_preset()}).status_code == 409


@pytest.mark.parametrize("name", ["Game", "has space", "a" * 33, "../x", "ไทย", ""])
def test_bad_preset_names_are_refused(env, name):
    assert env.post("/api/presets", {"name": name, **env.new_preset()}).status_code == 422


def test_replace_preset_keeps_its_place(env):
    r = env.put("/api/presets/game", env.new_preset(phrases=["เปิดเกมเลย"]))
    assert r.status_code == 200
    assert list(json.loads(env.presets_path.read_text("utf-8"))) == ["game", "work"]
    assert match("เปิดเกมเลย", env.engine.presets)[0] == "game"
    assert env.put("/api/presets/nope", env.new_preset()).status_code == 404
    assert env.put("/api/presets/game", {"name": "x", **env.new_preset()}).status_code == 422


def test_delete_preset(env):
    assert env.delete("/api/presets/work").status_code == 200
    assert list(json.loads(env.presets_path.read_text("utf-8"))) == ["game"]
    assert env.delete("/api/presets/work").status_code == 404
    assert env.delete("/api/presets/game").status_code == 409  # the file must keep one preset


def test_the_same_phrase_in_two_presets_is_refused_and_names_the_other_preset(env):
    before = env.presets_path.read_bytes()
    r = env.post("/api/presets", {"name": "notes", **env.new_preset(phrases=["เปิด โหมด เกม!"])})
    assert r.status_code == 422
    assert "'game'" in r.json()["fields"][0]["message"] and r.json()["fields"][0]["field"] == "phrases"
    assert env.presets_path.read_bytes() == before


def test_very_similar_phrases_are_saved_with_a_warning(env):
    # one letter different in the middle: not a fragment of the other, so both keep working
    r = env.post("/api/presets", {"name": "notes", **env.new_preset(phrases=["เปิดโหมดแกม"])})
    assert r.status_code == 201
    assert [(w["kind"], w["preset"], w["similar_to"]) for w in r.json()["warnings"]] == [("similar", "game", "เปิดโหมดเกม")]


# ---- SECURITY.md: presets written from the web ----

BAD_ACTIONS = [
    {"type": "uri", "target": "file:///C:/Windows/System32/calc.exe"},
    {"type": "uri", "target": "FILE:foo"},
    {"type": "uri", "target": "ms-msdt:/id PCWDiagnostic"},
    {"type": "uri", "target": "ms-settings:"},
    {"type": "uri", "target": "javascript:alert(1)"},
    {"type": "uri", "target": "search-ms:query=x"},
    {"type": "uri", "target": "no scheme here"},
    {"type": "uri", "target": "C:\\Windows\\System32\\calc.exe"},
    {"type": "uri", "target": "c:\\nonexistent\\evil.js"},
    {"type": "uri", "target": "D:/x/y.bat"},
    {"type": "uri", "target": "\\\\server\\share\\x.exe"},
    {"type": "chrome", "urls": ["javascript:alert(1)"]},
    {"type": "chrome", "urls": ["https://ok.example", "file:///C:/x"]},
    {"type": "chrome", "urls": ["https://a b.example"]},
    {"type": "chrome", "urls": []},
    {"type": "run", "path": EXE},  # a path in a preset: the program must come from programs.json
    {"type": "run", "path": EXE, "args": ["x"]},
    {"type": "run", "program": "tool", "args": ["x"]},  # args live in programs.json too
    {"type": "run", "program": "tool", "path": EXE},
    {"type": "run"},
    {"type": "run", "program": "nope"},  # not in programs.json
    {"type": "run", "program": "../tool"},
    {"type": "run", "program": "Tool"},
    {"type": "run", "program": ["tool"]},
    {"type": "open", "target": "relative\\file.txt"},
    {"type": "wait", "seconds": 31},
    {"type": "wait", "seconds": -1},
    {"type": "wait", "seconds": True},
    {"type": "format_disk"},
    {"type": "run", "program": "tool", "shell": True},
    {"type": "spending", "period": "year"},
]


@pytest.mark.parametrize("action", BAD_ACTIONS, ids=lambda a: json.dumps(a)[:50])
def test_dangerous_or_malformed_actions_are_refused_and_nothing_is_saved(env, action):
    before = env.presets_path.read_bytes()
    r = env.post("/api/presets", {"name": "bad", **env.new_preset(actions=[action])})
    assert r.status_code == 422, r.text
    assert r.json()["fields"]
    assert env.presets_path.read_bytes() == before
    assert "bad" not in env.engine.presets
    assert not (env.dir / "presets.json.bak").exists()


def test_valid_actions_of_every_type_are_accepted(env):
    actions = [
        {"type": "run", "program": "tool"},
        {"type": "open", "target": str(env.dir)},
        {"type": "uri", "target": "discord:"},
        {"type": "chrome", "urls": ["https://example.com", "http://localhost:3000/x?y=1"]},
        {"type": "wait", "seconds": 2.5},
        {"type": "spending", "period": "week"},
    ]
    r = env.post("/api/presets", {"name": "all", **env.new_preset(phrases=["ทดลองทุกอย่าง"], actions=actions)})
    assert r.status_code == 201, r.text
    assert env.engine.presets["all"]["actions"][0] == {"type": "run", "program": "tool"}


def test_open_paths_must_exist_and_the_error_does_not_echo_them(env, tmp_path):
    r = env.post("/api/presets", {"name": "x", **env.new_preset(actions=[{"type": "open", "target": str(tmp_path / "gone-folder")}])})
    assert r.status_code == 422
    assert r.json()["fields"] == [{"field": "actions.0.target", "message": "path not found"}]
    assert "gone-folder" not in r.text


def test_a_run_step_with_an_unknown_program_names_the_field(env):
    r = env.post("/api/presets", {"name": "x", **env.new_preset(actions=[{"type": "run", "program": "nope"}])})
    assert r.status_code == 422
    assert r.json()["fields"] == [{"field": "actions.0.program", "message": "unknown program"}]


def test_limits_on_phrases_reply_and_steps(env):
    def code(**over):
        return env.post("/api/presets", {"name": "lim", **env.new_preset(**over)}).status_code

    assert code(phrases=["ก" * 101]) == 422
    assert code(phrases=[f"คำสั่ง{i}" for i in range(21)]) == 422
    assert code(phrases=[]) == 422
    assert code(phrases=["!!!"]) == 422
    assert code(reply="ก" * 201) == 422
    assert code(actions=[{"type": "wait", "seconds": 0}] * 21) == 422
    assert code(phrases=["ก" * 100], reply="ก" * 200, actions=[{"type": "wait", "seconds": 30}] * 20) == 201


def test_a_field_called_path_keeps_its_name_in_the_error(env):
    r = env.post("/api/presets", {"name": "bad", **env.new_preset(actions=[{"type": "run", "program": "tool", "path": "calc.exe"}])})
    assert r.json()["fields"] == [{"field": "actions.0.path", "message": "Extra inputs are not permitted"}]


def test_validation_errors_name_the_field(env):
    r = env.post("/api/presets", {"name": "bad", **env.new_preset(actions=[{"type": "chrome", "urls": ["javascript:x"]}])})
    assert r.json()["fields"] == [{"field": "actions.0.urls", "message": "only http:// and https:// URLs are allowed"}]


# ---- test button ----

def test_test_button_runs_the_saved_preset_without_speaking(env):
    r = env.post("/api/presets/game/test")
    assert r.status_code == 200 and r.json() == {"started": True}
    assert env.engine.wait_idle()
    assert env.rig.events == ["run-game"] and env.rig.spoken == []
    entry = jarvis_log.read_day(jarvis_log.today(), env.logs)[-1]
    assert (entry["source"], entry["preset"], entry["result"]) == ("test", "game", "ok")


def test_test_button_ignores_any_body_and_runs_only_what_is_saved(env):
    evil = env.new_preset(actions=[{"type": "run", "path": EXE, "args": ["-c", "boom"]}])
    env.post("/api/presets/game/test", evil)
    assert env.engine.wait_idle()
    assert env.rig.events == ["run-game"]
    assert env.engine.presets["game"]["actions"] == PRESETS["game"]["actions"]


def test_test_button_unknown_or_busy(env):
    assert env.post("/api/presets/nope/test").status_code == 404
    assert env.post("/api/presets/BAD NAME/test").status_code == 422
    env.rig.hold_mic = True
    env.engine.set_armed(True)
    env.engine.toggle_listen("web")
    assert env.rig.recording.wait(2)
    assert env.post("/api/presets/game/test").status_code == 409
    env.rig.release.set()
    assert env.engine.wait_idle()


# ---- logs ----

def seed_log(env):
    e1 = jarvis_log.log_command("hotkey", "เปิดโหมดเกม", "game", 100.0, "ok", 2.0, directory=env.logs)
    e2 = jarvis_log.log_command("hotkey", "สวัสดีครับอากาศดีนะ", None, 40.0, "no_match", 1.0, directory=env.logs)
    return e1, e2


def test_logs_default_to_today_and_list_days(env):
    e1, e2 = seed_log(env)
    body = env.get("/api/logs").json()
    assert body["date"] == jarvis_log.today() and [e["id"] for e in body["entries"]] == [e1["id"], e2["id"]]
    assert env.get("/api/logs/dates").json() == {"dates": [jarvis_log.today()]}
    assert env.get("/api/logs?date=2020-01-01").json() == {"date": "2020-01-01", "entries": []}


@pytest.mark.parametrize("date", ["../secret", "2026-13-45", "today", "2026-1-1", "2026-10-31.jsonl"])
def test_bad_log_dates_are_refused(env, date):
    assert env.get("/api/logs", params={"date": date}).status_code == 422


def test_add_phrase_from_a_log_line_makes_it_match(env):
    _, miss = seed_log(env)
    assert match("สวัสดีครับอากาศดีนะ", env.engine.presets)[0] is None
    r = env.post(f"/api/logs/{miss['id']}/add-phrase", {"preset": "work"})
    assert r.status_code == 200 and r.json()["added"] is True
    assert match("สวัสดีครับอากาศดีนะ", env.engine.presets)[0] == "work"
    assert "สวัสดีครับอากาศดีนะ" in json.loads(env.presets_path.read_text("utf-8"))["work"]["phrases"]
    again = env.post(f"/api/logs/{miss['id']}/add-phrase", {"preset": "work"})
    assert again.status_code == 200 and again.json()["added"] is False


def test_add_phrase_rejections(env):
    hit, miss = seed_log(env)
    before = env.presets_path.read_bytes()
    assert env.post(f"/api/logs/{miss['id']}/add-phrase", {"preset": "nope"}).status_code == 404
    assert env.post("/api/logs/00000000-0000-4000-8000-000000000000/add-phrase", {"preset": "work"}).status_code == 404
    assert env.post("/api/logs/not-a-uuid/add-phrase", {"preset": "work"}).status_code == 422
    clash = env.post(f"/api/logs/{hit['id']}/add-phrase", {"preset": "work"})  # 'game' already owns that phrase
    assert clash.status_code == 422 and "'game'" in clash.json()["fields"][0]["message"]
    silent = jarvis_log.log_command("hotkey", "", None, None, "no_speech", 5.0, directory=env.logs)
    assert env.post(f"/api/logs/{silent['id']}/add-phrase", {"preset": "work"}).status_code == 422
    assert env.presets_path.read_bytes() == before


# ---- settings and hotkey ----

def test_settings_roundtrip_and_apply_without_restart(env):
    assert env.get("/api/settings").json() == Settings().to_dict()
    env.engine.set_armed(True)
    r = env.put("/api/settings", {"hotkey": "Right Ctrl", "silence_ms": 800, "beep": False, "match_threshold": 80})
    assert r.status_code == 200
    assert r.json()["hotkey"] == "right ctrl" and r.json()["match_threshold"] == 80.0
    saved = json.loads(env.settings_path.read_text("utf-8"))
    assert saved["silence_ms"] == 800 and saved["beep"] is False
    assert env.engine.settings.silence_ms == 800
    assert env.rig.hotkeys.calls[-1] == "right ctrl"
    assert env.get("/api/state").json()["hotkey"] == "right ctrl"


@pytest.mark.parametrize("body", [
    {"hotkey": "a"}, {"hotkey": "space"}, {"hotkey": "left shift"}, {"hotkey": 5},
    {"silence_ms": 10}, {"silence_ms": 1000.5}, {"max_seconds": 999}, {"match_threshold": 10},
    {"beep": "yes"}, {"unknown": 1},
])
def test_invalid_settings_are_refused_and_not_saved(env, body):
    assert env.put("/api/settings", body).status_code == 422
    assert not env.settings_path.exists()
    assert env.engine.settings == Settings()


def test_a_hotkey_the_keyboard_does_not_know_is_refused(env):
    env.engine._hotkeys.check = lambda key: "this key name is not recognized"
    r = env.put("/api/settings", {"hotkey": "ctrl+nonsense"})
    assert r.status_code == 422 and r.json()["fields"][0]["field"] == "hotkey"
    assert not env.settings_path.exists()


def test_hotkey_capture_returns_the_combo_and_saves_nothing(tmp_path):
    seen = []
    e = Env(tmp_path, capture=lambda seconds: seen.append(seconds) or "ctrl+alt+j")
    e.engine.set_armed(True)
    r = e.post("/api/hotkey/capture")
    assert r.json() == {"hotkey": "ctrl+alt+j", "ok": True, "reason": None}
    assert seen == [10]
    assert not e.settings_path.exists() and e.engine.settings.hotkey == "caps lock"
    assert e.rig.hotkeys.calls == ["caps lock", None, "caps lock"]  # paused while capturing, then restored
    e.engine.close()


def test_hotkey_capture_says_why_a_key_is_refused(tmp_path):
    e = Env(tmp_path, capture=lambda seconds: "a")
    body = e.post("/api/hotkey/capture").json()
    assert body["ok"] is False and "typing key" in body["reason"]
    e.engine.close()


def test_hotkey_capture_timeout(tmp_path):
    e = Env(tmp_path, capture=lambda seconds: None)
    r = e.post("/api/hotkey/capture")
    assert r.status_code == 200 and r.json() == {"hotkey": None, "ok": False, "reason": "timeout"}
    e.engine.close()


# ---- the real server ----

def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_server_binds_to_loopback_only_and_serves_over_http(tmp_path):
    e = Env(tmp_path)
    port = free_port()
    app = create_app(e.engine, PresetStore(e.presets_path), program_store=e.program_store, settings_path=e.settings_path,
                     logs_dir=e.logs, port=port, log=lambda *_: None)
    server = ApiServer(app, port)
    assert server.config.host == "127.0.0.1"
    server.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/state", timeout=5) as r:
            assert json.load(r)["state"] == "off"
        bad = urllib.request.Request(f"http://127.0.0.1:{port}/api/state", headers={"Host": "evil.example"})
        with pytest.raises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(bad, timeout=5)
        assert err.value.code == 403
        with pytest.raises(PortInUse):
            ensure_port_free(port)
    finally:
        server.stop()
        e.engine.close()
    ensure_port_free(port)


# ---- the static web UI (web/out/) ----

def web_env(tmp_path):
    out = tmp_path / "out"
    (out / "presets").mkdir(parents=True)
    (out / "index.html").write_text("<h1>home</h1>", encoding="utf-8")
    (out / "presets" / "index.html").write_text("<h1>presets</h1>", encoding="utf-8")
    (out / "_next").mkdir()
    (out / "_next" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("top secret", encoding="utf-8")
    return Env(tmp_path, web_dir=out)


def test_root_and_folder_pages_are_served(tmp_path):
    e = web_env(tmp_path)
    assert e.get("/").text == "<h1>home</h1>"
    assert e.get("/presets/").text == "<h1>presets</h1>"
    assert e.get("/presets").text == "<h1>presets</h1>"  # redirected to /presets/
    assert e.get("/_next/app.js").status_code == 200
    assert e.get("/nothing/").status_code == 404
    e.engine.close()


def test_web_pages_get_a_csp_and_revalidate_but_the_api_does_not(tmp_path):
    e = web_env(tmp_path)
    page = e.get("/")
    assert "default-src 'self'" in page.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in page.headers["content-security-policy"]
    assert page.headers["cache-control"] == "no-cache"
    assert "content-security-policy" not in e.get("/api/state").headers
    e.engine.close()


def test_the_api_wins_over_the_static_files_and_unknown_api_paths_are_404(tmp_path):
    e = web_env(tmp_path)
    assert e.get("/api/state").json()["state"] == "off"
    assert e.get("/api/nope").status_code == 404
    e.engine.close()


def test_static_files_cannot_escape_the_web_folder(tmp_path):
    e = web_env(tmp_path)
    for url in ("/../secret.txt", "/%2e%2e/secret.txt", "/..%2fsecret.txt", "/_next/../../secret.txt"):
        r = e.get(url)
        assert "top secret" not in r.text, url
    e.engine.close()


def test_static_files_still_need_the_right_host_and_refuse_writes(tmp_path):
    e = web_env(tmp_path)
    assert e.get("/", headers={"Host": "evil.example:3003"}).status_code == 403
    assert e.post("/").status_code == 405
    assert e.client.post("/", json={}).status_code == 403  # no X-Jarvis
    e.engine.close()


def test_without_a_build_the_root_explains_what_to_run(tmp_path):
    e = Env(tmp_path, web_dir=tmp_path / "missing")
    page = e.get("/")
    assert page.status_code == 200 and "npm run build" in page.text
    assert e.get("/api/state").status_code == 200
    e.engine.close()


def test_state_names_the_preset_while_it_runs(env):
    gate = threading.Event()
    started = threading.Event()

    def slow(presets, name, log=print):
        started.set()
        gate.wait(2)
        return 0

    env.engine._run_preset = slow
    env.post("/api/presets/game/test")
    assert started.wait(2)
    body = env.get("/api/state").json()
    assert (body["state"], body["preset"]) == ("running", "game")
    gate.set()
    assert env.engine.wait_idle()
    assert env.get("/api/state").json()["preset"] is None


def test_head_is_allowed_for_pages_only_and_still_needs_the_host(tmp_path):
    e = web_env(tmp_path)
    assert e.client.head("/presets/").status_code == 200  # the browser's link prefetch
    assert e.client.head("/api/state").status_code in (404, 405)  # API routes never answer HEAD
    assert e.client.head("/presets/", headers={"Host": "evil.example:3003"}).status_code == 403
    assert e.client.request("OPTIONS", "/presets/").status_code == 403
    e.engine.close()


def test_a_missing_file_and_a_duplicate_phrase_are_reported_together(env, tmp_path):
    ghost = str(tmp_path / "nothing-here")
    r = env.post("/api/presets", {"name": "x", **env.new_preset(phrases=["เปิดโหมดเกม"], actions=[{"type": "open", "target": ghost}])})
    assert r.status_code == 422
    assert {f["field"] for f in r.json()["fields"]} == {"actions.0.target", "phrases"}


# ---- mic test ----

def test_mic_test_endpoint(env):
    env.engine.set_armed(True)
    r = env.post("/api/mic/test")
    assert r.status_code == 200
    assert set(r.json()) == {"peak", "level", "noise", "threshold", "detects_speech"}
    assert env.rig.mic_calls == [3.0]
    assert env.get("/api/state").json()["state"] == "idle"


def test_mic_test_is_refused_while_the_master_switch_is_off(env):
    r = env.post("/api/mic/test")
    assert r.status_code == 409 and r.json()["error"] == "off"
    assert env.rig.mic_calls == []


def test_mic_test_needs_the_same_headers_as_any_post(env):
    env.engine.set_armed(True)
    assert env.post("/api/mic/test", headers={"Origin": "http://127.0.0.1:3003"}).status_code == 403
    assert env.client.get("/api/mic/test").status_code == 405 or env.client.get("/api/mic/test").status_code == 404
    assert env.rig.mic_calls == []


def test_a_missing_microphone_is_a_short_503(env):
    from jarvis.audio import AudioError

    def broken(seconds):
        raise AudioError("no microphone found at C:/secret/device")

    env.engine._record_fixed = broken
    env.engine.set_armed(True)
    r = env.post("/api/mic/test")
    assert r.status_code == 503 and r.json() == {"error": "no_microphone", "fields": []}
    assert "secret" not in r.text


# ---- a phrase must not break commands that work today ----

REAL = {
    "game": {"phrases": ["เปิดโหมดเกม", "โหมดเล่นเกม", "โหมดเกม"], "reply": "x", "actions": []},
    "work": {"phrases": ["เปิดโหมดทำงาน", "โหมดทำงาน", "โหมดงาน"], "reply": "x", "actions": []},
}


def real_env(tmp_path):
    e = Env(tmp_path)
    e.engine.reload_presets(json.loads(json.dumps(REAL)))
    e.presets_path.write_text(json.dumps(REAL, ensure_ascii=False, indent=2), encoding="utf-8")
    return e


def combined(env, preset, phrase):
    entry = jarvis_log.log_command("hotkey", phrase, None, 100.0, "no_match", 5.0, directory=env.logs)
    return env.post(f"/api/logs/{entry['id']}/add-phrase", {"preset": preset})


@pytest.mark.parametrize("preset, phrase, broken", [
    ("work", "เปิดโหมดเกม โหมดทำงาน", "โหมดเกม"),
    ("game", "เปิดโหมดเกม และเปิดโหมดทำงาน", "โหมดทำงาน"),
    ("work", "เปิดโหมดเกมส์", "เปิดโหมดเกม"),
])
def test_adding_a_phrase_that_would_break_another_command_is_refused(tmp_path, preset, phrase, broken):
    e = real_env(tmp_path)
    before = e.presets_path.read_bytes()
    r = combined(e, preset, phrase)
    assert r.status_code == 422
    messages = [f["message"] for f in r.json()["fields"]]
    assert any(m.startswith("saving this would stop Jarvis recognising") and f"'{broken}'" in m for m in messages)
    assert any(m.startswith(f"'{phrase}'") for m in messages)  # and the phrase itself would never match
    assert e.presets_path.read_bytes() == before
    assert phrase not in e.engine.presets[preset]["phrases"]
    for name, p in e.engine.presets.items():  # every command still works
        for known in p["phrases"]:
            assert match(known, e.engine.presets)[0] == name
    e.engine.close()


def test_a_harmless_phrase_can_still_be_added_from_the_log(tmp_path):
    e = real_env(tmp_path)
    r = combined(e, "work", "เปิดโหมดทำงานให้หน่อย")
    assert r.status_code == 200 and r.json()["added"] is True and r.json()["warnings"] == []
    assert match("เปิดโหมดทำงานให้หน่อย", e.engine.presets)[0] == "work"
    e.engine.close()


def test_the_editor_refuses_regressions_and_warns_about_a_phrase_that_cannot_match(tmp_path):
    e = real_env(tmp_path)
    work = {**REAL["work"], "phrases": REAL["work"]["phrases"] + ["เปิดโหมดเกม โหมดทำงาน"]}
    r = e.put("/api/presets/work", work)
    assert r.status_code == 422
    assert any("stop Jarvis recognising 'โหมดเกม'" in f["message"] for f in r.json()["fields"])
    # the combined phrase as its own preset breaks 'โหมดทำงาน' too
    both = e.post("/api/presets", {"name": "both", **e.new_preset(phrases=["เปิดโหมดเกม และเปิดโหมดทำงาน"])})
    assert both.status_code == 422
    # a phrase that only contains one of them breaks nothing: saved, with a warning that it cannot match
    r = e.post("/api/presets", {"name": "done", **e.new_preset(phrases=["เปิดโหมดงานเสร็จแล้วนะ"])})
    assert r.status_code == 201, r.text
    assert [(w["kind"], w["phrase"]) for w in r.json()["warnings"]] == [("unmatchable", "เปิดโหมดงานเสร็จแล้วนะ")]
    e.engine.close()


def test_a_preset_that_already_has_a_broken_phrase_is_told_so_on_the_next_save(tmp_path):
    e = real_env(tmp_path)
    broken = json.loads(json.dumps(REAL))
    broken["game"]["phrases"].append("เปิดโหมดเกม และเปิดโหมดทำงาน")
    broken["work"]["phrases"].append("เปิดโหมดเกม โหมดทำงาน")
    e.engine.reload_presets(broken)  # what the file looked like after both were added
    r = e.put("/api/presets/game", {k: v for k, v in broken["game"].items()})
    assert r.status_code == 201 or r.status_code == 200
    kinds = {(w["kind"], w["phrase"]) for w in r.json()["warnings"] if w["kind"] == "unmatchable"}
    assert ("unmatchable", "เปิดโหมดเกม และเปิดโหมดทำงาน") in kinds
    assert ("unmatchable", "โหมดเกม") in kinds or ("unmatchable", "เปิดโหมดเกม") in kinds
    e.engine.close()


# ---- open: only folders and a short list of document and media types ----

OPEN_OK = ["pdf", "txt", "md", "docx", "xlsx", "pptx", "png", "jpg", "jpeg", "gif", "mp3", "mp4", "PDF", "Jpg"]
OPEN_NOT_ALLOWED = "only folders and these files can be opened from the web: pdf, txt, md, docx, xlsx, pptx, png, jpg, jpeg, gif, mp3, mp4"


def open_preset(env, target, name="doc"):
    return env.post("/api/presets", {"name": name, **env.new_preset(actions=[{"type": "open", "target": str(target)}])})


@pytest.mark.parametrize("suffix", OPEN_OK)
def test_open_accepts_documents_and_media(env, tmp_path, suffix):
    f = tmp_path / f"file.{suffix}"
    f.write_text("x", encoding="utf-8")
    assert open_preset(env, f).status_code == 201


def test_open_accepts_a_folder(env, tmp_path):
    assert open_preset(env, tmp_path).status_code == 201


@pytest.mark.parametrize("name", [
    "a.bat", "a.cmd", "a.ps1", "a.vbs", "a.js", "a.hta", "a.msi", "a.lnk", "a.url", "a.exe", "a.com", "a.scr",
    "a.reg", "a.html", "a.svg", "A.BAT", "noextension", "a.pdf.exe", "a.txt.bat",
])
def test_open_refuses_everything_else(env, tmp_path, name):
    f = tmp_path / name
    f.write_text("x", encoding="utf-8")
    before = env.presets_path.read_bytes()
    r = open_preset(env, f)
    assert r.status_code == 422, name
    assert r.json()["fields"] == [{"field": "actions.0.target", "message": OPEN_NOT_ALLOWED}]
    assert env.presets_path.read_bytes() == before and "doc" not in env.engine.presets


def test_a_program_from_the_system_folder_cannot_be_opened_either(env):
    calc = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "calc.exe")
    assert open_preset(env, calc).status_code == 422


def test_trailing_dots_and_spaces_do_not_hide_a_script(env, tmp_path):
    script = tmp_path / "x.bat"
    script.write_text("echo hi", encoding="utf-8")
    assert open_preset(env, str(script) + ".").status_code == 422  # Windows would open x.bat


def test_a_link_named_like_a_document_is_judged_by_where_it_points(env, tmp_path):
    link = tmp_path / "innocent.pdf"
    try:
        os.symlink(EXE, link)
    except OSError:
        pytest.skip("creating symbolic links needs a privilege this account does not have")
    assert open_preset(env, link).status_code == 422


def test_open_judges_the_resolved_path_not_the_name(env, tmp_path, monkeypatch):
    """A link called innocent.pdf that resolves to a program is refused (realpath is simulated here)."""
    link = tmp_path / "innocent.pdf"
    link.write_text("x", encoding="utf-8")
    monkeypatch.setattr("jarvis.models.os.path.realpath", lambda p: str(p).replace("innocent.pdf", "payload.exe"))
    assert open_preset(env, link).status_code == 422


def test_the_other_problems_of_a_refused_preset_are_still_reported(env, tmp_path):
    script = tmp_path / "x.bat"
    script.write_text("echo hi", encoding="utf-8")
    actions = [{"type": "open", "target": str(script)}, {"type": "run", "program": "nope"}]
    r = env.post("/api/presets", {"name": "two", **env.new_preset(actions=actions)})
    assert {f["field"] for f in r.json()["fields"]} == {"actions.0.target", "actions.1.program"}


def test_a_hand_edited_presets_file_may_still_open_a_shortcut(tmp_path):
    """The allow-list guards the web, not presets.json: whoever edits the file can already do anything."""
    data = {"x": {"phrases": ["ทดสอบ"], "reply": "", "actions": [{"type": "open", "target": "C:\\Users\\me\\app.lnk"}]}}
    assert validate_presets(data)["x"]["actions"][0]["type"] == "open"


# ---- programs.json: the allow-list for `run` ----

SYSTEM32 = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
CALC = os.path.join(SYSTEM32, "calc.exe")


def add_program(env, **over):
    return env.post("/api/programs", {"name": "calc", "path": CALC, "args": ["--x", "y z"], **over})


def test_list_programs(env):
    assert env.get("/api/programs").json() == {"programs": [{"name": "tool", "path": EXE, "args": []}]}


def test_a_run_step_names_a_program_and_the_preset_is_saved(env):
    r = env.post("/api/presets", {"name": "p", **env.new_preset()})
    assert r.status_code == 201
    assert json.loads(env.presets_path.read_text("utf-8"))["p"]["actions"] == [{"type": "run", "program": "tool"}]


def test_adding_a_program_asks_the_person_and_saves_it_on_yes(env):
    r = add_program(env)
    assert r.status_code == 201 and r.json() == {"name": "calc"}
    assert env.asked == [("calc", os.path.realpath(CALC), ["--x", "y z"])]  # the real path and every argument
    saved = json.loads(env.programs_path.read_text("utf-8"))
    assert saved["calc"] == {"path": CALC, "args": ["--x", "y z"]} and "tool" in saved
    assert env.program_store.programs["calc"]["args"] == ["--x", "y z"]  # in use at once
    assert env.get("/api/programs").json()["programs"][-1]["name"] == "calc"
    assert (env.dir / "programs.json.bak").exists() and not (env.dir / "programs.json.tmp").exists()


def test_no_means_the_program_is_not_added(env):
    env.answer = "no"
    before = env.programs_path.read_bytes()
    r = add_program(env)
    assert r.status_code == 403 and r.json()["error"] == "declined"
    assert env.programs_path.read_bytes() == before and "calc" not in env.program_store.programs
    assert len(env.asked) == 1


def test_no_answer_in_time_means_no(env):
    env.answer = "timeout"
    before = env.programs_path.read_bytes()
    r = add_program(env)
    assert r.status_code == 403 and r.json()["error"] == "no_answer"
    assert env.programs_path.read_bytes() == before and "calc" not in env.program_store.programs


def test_a_program_that_was_refused_cannot_be_used_by_a_preset(env):
    env.answer = "no"
    add_program(env)
    r = env.post("/api/presets", {"name": "p", **env.new_preset(actions=[{"type": "run", "program": "calc"}])})
    assert r.status_code == 422 and r.json()["fields"][0]["message"] == "unknown program"


@pytest.mark.parametrize("over", [
    {"path": "calc.exe"},  # not absolute
    {"path": os.path.join(SYSTEM32, "drivers", "etc", "hosts")},  # not an .exe
    {"path": os.path.join(SYSTEM32, "does-not-exist.exe")},
    {"name": "Calc"}, {"name": "../calc"}, {"name": ""}, {"name": "x" * 33},
    {"args": ["x"] * 21}, {"args": ["x" * 501]}, {"args": "not a list"}, {"args": [1]},
    {"extra": 1}, {"path": ""},
])
def test_an_invalid_request_never_opens_a_box(env, over):
    before = env.programs_path.read_bytes()
    r = add_program(env, **over)
    assert r.status_code == 422, over
    assert env.asked == [] and env.programs_path.read_bytes() == before


def test_a_missing_file_error_does_not_echo_the_path(env):
    r = add_program(env, path=os.path.join(SYSTEM32, "secret-folder", "nope.exe"))
    assert r.json()["fields"] == [{"field": "path", "message": "file not found"}]
    assert "secret-folder" not in r.text


def test_a_name_that_exists_is_a_conflict_and_opens_no_box(env):
    r = add_program(env, name="tool")
    assert r.status_code == 409 and r.json()["error"] == "exists" and env.asked == []


def test_a_second_request_while_a_box_is_open_gets_409(tmp_path):
    gate, started, calls = threading.Event(), threading.Event(), []

    def slow(name, path, args):
        calls.append(name)
        started.set()
        gate.wait(5)
        return "yes"

    e = Env(tmp_path, confirm=slow)
    first = []
    t = threading.Thread(target=lambda: first.append(add_program(e)))
    t.start()
    assert started.wait(3)
    second = add_program(e, name="other")
    assert second.status_code == 409 and second.json()["error"] == "busy"
    assert calls == ["calc"]  # no second box
    gate.set()
    t.join(5)
    assert first[0].status_code == 201
    assert add_program(e, name="other").status_code == 201  # free again
    e.engine.close()


def test_the_person_decides_even_for_a_shell(env):
    """There is no deny-list any more: the box is the control, and it shows exactly what would be added."""
    cmd = os.path.join(SYSTEM32, "cmd.exe")
    r = add_program(env, name="shell", path=cmd, args=["/c", "echo", "hi"])
    assert r.status_code == 201
    assert env.asked[0][1].lower() == os.path.realpath(cmd).lower() and env.asked[0][2] == ["/c", "echo", "hi"]


def test_deleting_a_program_needs_no_box(env):
    add_program(env)
    env.asked.clear()
    r = env.delete("/api/programs/calc")
    assert r.status_code == 200 and env.asked == []
    assert "calc" not in json.loads(env.programs_path.read_text("utf-8"))
    assert env.delete("/api/programs/calc").status_code == 404


def test_a_program_a_preset_uses_cannot_be_deleted(env):
    env.post("/api/presets", {"name": "p", **env.new_preset()})
    r = env.delete("/api/programs/tool")
    assert r.status_code == 409 and r.json()["error"] == "in_use"
    assert "'p'" in r.json()["fields"][0]["message"]
    assert "tool" in env.program_store.programs
    env.delete("/api/presets/p")
    assert env.delete("/api/programs/tool").status_code == 200  # free once nothing uses it


def test_program_names_in_the_url_are_validated(env):
    assert env.delete("/api/programs/..%2Ftool").status_code in (404, 405, 422)
    assert env.delete("/api/programs/Tool").status_code == 422


def test_programs_endpoints_need_the_same_headers_as_any_write(env):
    assert env.client.post("/api/programs", json={"name": "calc", "path": CALC}, headers={"Origin": BASE}).status_code == 403
    assert env.client.post("/api/programs", json={"name": "calc", "path": CALC}, headers={"X-Jarvis": "1", "Origin": "https://evil.example"}).status_code == 403
    assert env.client.delete("/api/programs/tool").status_code == 403
    assert env.asked == [] and "tool" in env.program_store.programs


def test_the_test_button_runs_the_programs_the_preset_names(env):
    env.post("/api/presets", {"name": "p", **env.new_preset()})
    assert env.post("/api/presets/p/test").status_code == 200
    assert env.engine.wait_idle()
    assert env.rig.events == ["run-p"]  # the engine's runner got the saved preset, never a request body
