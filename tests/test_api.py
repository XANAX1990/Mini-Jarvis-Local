import json
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
    def __init__(self, tmp_path, dev=False, capture=None, web_dir=None):
        self.dir = tmp_path
        self.presets_path = tmp_path / "presets.json"
        self.presets_path.write_text(json.dumps(PRESETS, ensure_ascii=False, indent=2), encoding="utf-8")
        self.logs = tmp_path / "logs"
        self.settings_path = tmp_path / "settings.json"
        self.rig = Rig(presets=validate_presets(json.loads(self.presets_path.read_text("utf-8"))))
        self.engine = self.rig.engine
        self.rig.log_command = lambda *a: jarvis_log.log_command(*a, directory=self.logs)
        self.engine._log_command = self.rig.log_command
        self.app = create_app(
            self.engine, PresetStore(self.presets_path), settings_path=self.settings_path,
            logs_dir=self.logs, dev=dev, capture=capture, web_dir=web_dir, log=lambda *_: None,
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
        return {"phrases": ["เปิดโน้ต"], "reply": "ได้เลย", "actions": [{"type": "run", "path": EXE}], **over}


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
    r = env.post("/api/presets", {"name": "notes", **env.new_preset(phrases=["เปิดโหมดเกมส์"])})
    assert r.status_code == 201
    assert [(w["preset"], w["similar_to"]) for w in r.json()["warnings"]] == [("game", "เปิดโหมดเกม")]


# ---- SECURITY.md: presets written from the web ----

BAD_ACTIONS = [
    {"type": "uri", "target": "file:///C:/Windows/System32/calc.exe"},
    {"type": "uri", "target": "FILE:foo"},
    {"type": "uri", "target": "ms-msdt:/id PCWDiagnostic"},
    {"type": "uri", "target": "ms-settings:"},
    {"type": "uri", "target": "javascript:alert(1)"},
    {"type": "uri", "target": "search-ms:query=x"},
    {"type": "uri", "target": "no scheme here"},
    {"type": "chrome", "urls": ["javascript:alert(1)"]},
    {"type": "chrome", "urls": ["https://ok.example", "file:///C:/x"]},
    {"type": "chrome", "urls": ["https://a b.example"]},
    {"type": "chrome", "urls": []},
    {"type": "run", "path": "calc.exe"},
    {"type": "run", "path": "C:\\Windows\\System32\\cmd.bat"},
    {"type": "run", "path": EXE, "args": ["x"] * 21},
    {"type": "run", "path": EXE, "args": ["x" * 501]},
    {"type": "run", "path": EXE, "args": "not a list"},
    {"type": "open", "target": "relative\\file.txt"},
    {"type": "wait", "seconds": 31},
    {"type": "wait", "seconds": -1},
    {"type": "wait", "seconds": True},
    {"type": "format_disk"},
    {"type": "run", "path": EXE, "shell": True},
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
        {"type": "run", "path": f'"{EXE}"', "args": ["--x", "y z"]},  # quotes from "Copy as path" are stripped
        {"type": "open", "target": str(env.dir)},
        {"type": "uri", "target": "discord:"},
        {"type": "chrome", "urls": ["https://example.com", "http://localhost:3000/x?y=1"]},
        {"type": "wait", "seconds": 2.5},
        {"type": "spending", "period": "week"},
    ]
    r = env.post("/api/presets", {"name": "all", **env.new_preset(phrases=["ทดลองทุกอย่าง"], actions=actions)})
    assert r.status_code == 201, r.text
    assert env.engine.presets["all"]["actions"][0]["path"] == EXE


def test_run_and_open_paths_must_exist(env, tmp_path):
    ghost = str(tmp_path / "nothing.exe")
    r = env.post("/api/presets", {"name": "x", **env.new_preset(actions=[{"type": "run", "path": ghost}])})
    assert r.status_code == 422
    assert r.json()["fields"] == [{"field": "actions.0.path", "message": "file not found"}]
    assert "nothing" not in r.text
    r = env.post("/api/presets", {"name": "x", **env.new_preset(actions=[{"type": "open", "target": str(tmp_path / "gone")}])})
    assert r.json()["fields"][0]["field"] == "actions.0.target"


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
    r = env.post("/api/presets", {"name": "bad", **env.new_preset(actions=[{"type": "run", "path": "calc.exe"}])})
    assert r.json()["fields"] == [{"field": "actions.0.path", "message": "must be an absolute path"}]


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
    assert e.post("/api/hotkey/capture").status_code == 408
    e.engine.close()


# ---- the real server ----

def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_server_binds_to_loopback_only_and_serves_over_http(tmp_path):
    e = Env(tmp_path)
    port = free_port()
    app = create_app(e.engine, PresetStore(e.presets_path), settings_path=e.settings_path,
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
