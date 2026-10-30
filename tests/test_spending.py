import json
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from zoneinfo import ZoneInfo

import pytest

from jarvis import spending
from jarvis.presets import PresetError, spending_period, spoken_reply, validate_presets
from jarvis.spending import SAY_CANNOT_CONNECT, SAY_DOWN, SpendingError, answer, date_range, sentence

BKK = ZoneInfo("Asia/Bangkok")


def at(y, m, d, h=12, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=BKK)


# ---- dates (Asia/Bangkok) ----

def test_today():
    assert date_range("today", at(2026, 10, 31)) == ("2026-10-31", "2026-10-31")


def test_week_runs_from_monday_to_today():
    # 2026-10-31 is a Saturday: Monday is the 26th
    assert date_range("week", at(2026, 10, 31)) == ("2026-10-26", "2026-10-31")


def test_week_on_a_monday_is_just_that_day():
    assert date_range("week", at(2026, 10, 26)) == ("2026-10-26", "2026-10-26")


def test_week_on_a_sunday_reaches_back_six_days():
    assert date_range("week", at(2026, 11, 1)) == ("2026-10-26", "2026-11-01")


def test_week_can_start_in_the_previous_month():
    assert date_range("week", at(2026, 11, 3)) == ("2026-11-02", "2026-11-03")
    assert date_range("week", at(2026, 12, 2)) == ("2026-11-30", "2026-12-02")


def test_month_starts_on_the_first():
    assert date_range("month", at(2026, 10, 31)) == ("2026-10-01", "2026-10-31")


def test_the_date_is_taken_in_bangkok_not_utc():
    # 17:30 UTC on Saturday the 31st is already 00:30 on Sunday the 1st in Bangkok
    late = datetime(2026, 10, 31, 17, 30, tzinfo=timezone.utc)
    assert date_range("today", late) == ("2026-11-01", "2026-11-01")
    assert date_range("month", late) == ("2026-11-01", "2026-11-01")


def test_unknown_period_is_refused():
    with pytest.raises(ValueError):
        date_range("year", at(2026, 10, 31))


# ---- the sentence ----

def test_sentence_writes_money_and_count_as_thai_words():
    s = sentence("month", {"total": 4350.0, "count": 32})
    assert s == "เดือนนี้จ่ายไป สี่พันสามร้อยห้าสิบบาทถ้วน จาก สามสิบสอง รายการ"
    assert not any(ch.isdigit() for ch in s)


def test_sentence_says_satang_when_there_are_any():
    assert "ห้าสิบสตางค์" in sentence("today", {"total": 120.5, "count": 1})


def test_each_period_has_its_own_opening():
    summary = {"total": 100, "count": 1}
    assert sentence("today", summary).startswith("วันนี้จ่ายไป")
    assert sentence("week", summary).startswith("อาทิตย์นี้จ่ายไป")
    assert sentence("month", summary).startswith("เดือนนี้จ่ายไป")


@pytest.mark.parametrize("period,said", [("today", "วันนี้"), ("week", "อาทิตย์นี้"), ("month", "เดือนนี้")])
def test_zero_spending(period, said):
    assert sentence(period, {"total": 0, "count": 0}) == f"{said}ยังไม่มีรายจ่าย"


# ---- answer(): never raises, details only in the log ----

def test_answer_uses_the_dates_of_the_period():
    seen = []

    def fake(first, last):
        seen.append((first, last))
        return {"total": 10, "count": 1}

    answer("week", at(2026, 10, 31), fetch=fake)
    assert seen == [("2026-10-26", "2026-10-31")]


def test_answer_when_the_api_is_down_logs_the_detail_but_says_it_short():
    logged = []

    def down(first, last):
        raise SpendingError("Slip Tracker is not reachable (ConnectionRefusedError)", SAY_DOWN)

    assert answer("month", at(2026, 10, 31), fetch=down, log=logged.append) == "ระบบสลิปยังไม่เปิด"
    assert "ConnectionRefusedError" in logged[0]


def test_answer_survives_a_bug_in_the_fetch():
    def boom(first, last):
        raise KeyError("secret-token-value")

    logged = []
    assert answer("today", at(2026, 10, 31), fetch=boom, log=logged.append) == SAY_CANNOT_CONNECT
    assert "secret-token-value" not in logged[0]  # only the exception type is logged


# ---- the real HTTP call, against a throwaway local server ----

class Handler(BaseHTTPRequestHandler):
    requests = []
    mode = "ok"

    def do_GET(self):
        Handler.requests.append((self.path, self.headers.get("X-Local-Token")))
        if Handler.mode == "401":
            self.send_response(401)
            self.end_headers()
            return
        body = b"not json" if Handler.mode == "garbage" else json.dumps(
            {"from": "a", "to": "b", "count": 32, "total": 4350.0, "by_category": []}
        ).encode()
        self.send_response(200 if Handler.mode != "500" else 500)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def server():
    Handler.requests, Handler.mode = [], "ok"
    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def env_for(url, token="tok-123"):
    return {"SLIPS_API_URL": url, "SLIPS_API_TOKEN": token}


def test_fetch_sends_the_token_and_the_date_range(server):
    data = spending.fetch_summary("2026-10-01", "2026-10-31", env=env_for(server))
    assert (data["count"], data["total"]) == (32, 4350.0)
    assert Handler.requests == [("/summary?from=2026-10-01&to=2026-10-31", "tok-123")]


def test_wrong_token_is_a_401_and_is_said_as_cannot_connect(server):
    Handler.mode = "401"
    with pytest.raises(SpendingError) as e:
        spending.fetch_summary("2026-10-01", "2026-10-31", env=env_for(server, "wrong"))
    assert e.value.spoken == SAY_CANNOT_CONNECT
    assert "401" in str(e.value) and "wrong" not in str(e.value)


@pytest.mark.parametrize("mode", ["500", "garbage"])
def test_server_error_and_garbage_are_cannot_connect(server, mode):
    Handler.mode = mode
    with pytest.raises(SpendingError) as e:
        spending.fetch_summary("2026-10-01", "2026-10-31", env=env_for(server))
    assert e.value.spoken == SAY_CANNOT_CONNECT


def test_api_not_running_is_said_as_not_open():
    httpd = HTTPServer(("127.0.0.1", 0), Handler)  # take a free port, then close it: nothing listens
    url = f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.server_close()
    with pytest.raises(SpendingError) as e:
        spending.fetch_summary("2026-10-01", "2026-10-31", env=env_for(url), timeout=2)
    assert e.value.spoken == SAY_DOWN


def test_a_missing_token_never_reaches_the_network():
    with pytest.raises(SpendingError) as e:
        spending.fetch_summary("2026-10-01", "2026-10-31", env={"SLIPS_API_URL": "http://127.0.0.1:1"})
    assert e.value.spoken == SAY_CANNOT_CONNECT and "SLIPS_API_TOKEN" in str(e.value)


@pytest.mark.parametrize("url", ["https://example.com", "http://192.168.1.5:8000", "http://evil.test", "ftp://127.0.0.1"])
def test_the_token_is_only_sent_to_this_pc(url):
    with pytest.raises(SpendingError) as e:
        spending.fetch_summary("2026-10-01", "2026-10-31", env=env_for(url))
    assert "stays on this PC" in str(e.value)


def test_default_address_is_loopback(monkeypatch):
    assert spending.DEFAULT_URL == "http://127.0.0.1:8000"
    assert spending._api_url({}) == "http://127.0.0.1:8000"


# ---- .env ----

def test_load_env_reads_values_and_keeps_real_environment(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text('# comment\nSLIPS_API_URL="http://127.0.0.1:8000"\nSLIPS_API_TOKEN=abc\n\nBAD LINE\n', encoding="utf-8")
    monkeypatch.delenv("SLIPS_API_URL", raising=False)
    monkeypatch.setenv("SLIPS_API_TOKEN", "from-real-env")
    spending.load_env(f)
    import os

    assert os.environ["SLIPS_API_URL"] == "http://127.0.0.1:8000"
    assert os.environ["SLIPS_API_TOKEN"] == "from-real-env"
    monkeypatch.delenv("SLIPS_API_URL")


def test_missing_env_file_is_fine(tmp_path):
    spending.load_env(tmp_path / "nope.env")


# ---- presets ----

def preset(*actions, reply="ได้เลย"):
    return {"phrases": ["เดือนนี้จ่ายไปเท่าไร"], "reply": reply, "actions": list(actions)}


def test_spending_action_is_valid_for_known_periods():
    for period in ("today", "week", "month"):
        validate_presets({"s": preset({"type": "spending", "period": period})})


@pytest.mark.parametrize("bad", [{"type": "spending"}, {"type": "spending", "period": "year"}, {"type": "spending", "period": 3}])
def test_spending_action_needs_a_known_period(bad):
    with pytest.raises(PresetError):
        validate_presets({"s": preset(bad)})


def test_spoken_reply_is_the_fixed_reply_without_a_spending_action():
    p = preset({"type": "wait", "seconds": 0}, reply="เปิดโหมดเกมแล้ว")
    assert spending_period(p) is None
    assert spoken_reply(p) == "เปิดโหมดเกมแล้ว"


def test_spoken_reply_is_the_live_answer_for_a_spending_preset(monkeypatch):
    monkeypatch.setattr(spending, "load_env", lambda *a, **k: None)
    monkeypatch.setattr(spending, "answer", lambda period: f"answer for {period}")
    assert spoken_reply(preset({"type": "spending", "period": "week"})) == "answer for week"
