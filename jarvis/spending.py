"""Answer "how much did I spend?" from the Slip Tracker API on this PC (read only).

Speech only picks a preset (`spending-today`, `-week`, `-month`); this module turns the period into
dates, asks the local API, and builds one Thai sentence for the voice. The API address and token come
from this project's `.env` (SLIPS_API_URL, SLIPS_API_TOKEN), never from presets.json or from speech.
Spoken answers are short on purpose: details (status codes, error text) go to the log, the token never does.
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from pythainlp.util import bahttext, num_to_thaiword

BANGKOK = ZoneInfo("Asia/Bangkok")
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
DEFAULT_URL = "http://127.0.0.1:8000"
LOCAL_HOSTS = ("127.0.0.1", "localhost")  # the token is only ever sent to this PC
TIMEOUT_SECONDS = 5
PERIODS = {"today": "วันนี้", "week": "อาทิตย์นี้", "month": "เดือนนี้"}

SAY_DOWN = "ระบบสลิปยังไม่เปิด"
SAY_CANNOT_CONNECT = "เชื่อมระบบสลิปไม่ได้"


class SpendingError(Exception):
    """The API could not be read. `spoken` is what Jarvis says; the message is for the log."""

    def __init__(self, message, spoken):
        super().__init__(message)
        self.spoken = spoken


def load_env(path=ENV_PATH):
    """Read KEY=VALUE lines from .env into os.environ (variables already set win)."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def date_range(period, now=None):
    """(first, last) as YYYY-MM-DD in Bangkok time: today / this week (Monday to today) / this month."""
    if period not in PERIODS:
        raise ValueError(f"unknown period {period!r}")
    today = (now or datetime.now(BANGKOK)).astimezone(BANGKOK).date()
    if period == "week":
        first = today - timedelta(days=today.weekday())
    elif period == "month":
        first = today.replace(day=1)
    else:
        first = today
    return first.isoformat(), today.isoformat()


def _api_url(env):
    base = (env.get("SLIPS_API_URL") or DEFAULT_URL).rstrip("/")
    parsed = urllib.parse.urlparse(base)
    if parsed.scheme != "http" or parsed.hostname not in LOCAL_HOSTS:
        raise SpendingError(
            "SLIPS_API_URL must be http://127.0.0.1 or http://localhost (the token stays on this PC)",
            SAY_CANNOT_CONNECT,
        )
    return base


def fetch_summary(first, last, env=None, timeout=TIMEOUT_SECONDS):
    """GET /summary?from=&to= from the Slip Tracker API. Raises SpendingError, never leaks the token."""
    env = os.environ if env is None else env
    token = env.get("SLIPS_API_TOKEN")
    if not token:
        raise SpendingError("SLIPS_API_TOKEN is not set in .env", SAY_CANNOT_CONNECT)
    url = f"{_api_url(env)}/summary?" + urllib.parse.urlencode({"from": first, "to": last})
    request = urllib.request.Request(url, headers={"X-Local-Token": token})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.load(response)
    except urllib.error.HTTPError as e:  # before URLError: it is a subclass
        raise SpendingError(f"Slip Tracker answered HTTP {e.code}", SAY_CANNOT_CONNECT) from None
    except (urllib.error.URLError, OSError) as e:  # refused, timed out, no route
        reason = getattr(e, "reason", e)
        raise SpendingError(f"Slip Tracker is not reachable ({type(reason).__name__})", SAY_DOWN) from None
    except ValueError:
        raise SpendingError("Slip Tracker sent something that is not JSON", SAY_CANNOT_CONNECT) from None
    ok = (
        isinstance(data, dict)
        and isinstance(data.get("total"), (int, float))
        and isinstance(data.get("count"), int)
    )
    if not ok:
        raise SpendingError("Slip Tracker's answer has no total and count", SAY_CANNOT_CONNECT)
    return data


def sentence(period, summary):
    """One Thai sentence. Digits are written as words because the Thai voice reads them badly."""
    when = PERIODS[period]
    if summary["count"] == 0 or summary["total"] <= 0:
        return f"{when}ยังไม่มีรายจ่าย"
    return f"{when}จ่ายไป {bahttext(summary['total'])} จาก {num_to_thaiword(summary['count'])} รายการ"


def answer(period, now=None, fetch=fetch_summary, log=print):
    """What Jarvis says for `period`. Never raises: a problem becomes a short spoken line plus a log line."""
    try:
        first, last = date_range(period, now)
        return sentence(period, fetch(first, last))
    except SpendingError as e:
        log(f"spending {period}: {e}")
        return e.spoken
    except Exception as e:  # a bug here must not stop Jarvis from listening
        log(f"spending {period}: unexpected {type(e).__name__}")
        return SAY_CANNOT_CONNECT
