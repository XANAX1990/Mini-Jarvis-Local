"""Write one JSON line per command into logs/YYYY-MM-DD.jsonl, and keep logs for a limited time.

Each entry: id (uuid4), time (ISO, Asia/Bangkok), source (hotkey | web | test), transcript, preset,
score, result (ok | no_match | no_speech | error), seconds. The file is named by the Bangkok date.

Transcripts are what people said near the microphone, so they are not kept for ever:
`prune_daily_logs()` (when `listen` starts) drops day files older than RETENTION_DAYS, and the older
formats are pruned too: `prune_command_files()` (logs/commands/), `prune_commands()`
(logs/commands.jsonl) and `prune_text_log()` (listen.log, before it is opened). They are not migrated.
logs/ is never committed (see .gitignore).
"""
import json
import os
import re
import tempfile
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

LOG_PATH = Path(__file__).resolve().parent.parent / "logs" / "commands.jsonl"
LOGS_DIR = LOG_PATH.parent
RETENTION_DAYS = 30
TIMEZONE = ZoneInfo("Asia/Bangkok")

COMMANDS_DIR = LOG_PATH.parent / "commands"
_FILE_STAMP = "%Y-%m-%d_%H-%M-%S"
_DAY_FILE = re.compile(r"\d{4}-\d{2}-\d{2}\.jsonl")


def log_command(source, transcript, preset, score, result, seconds, directory=None, now=None):
    """Append this command to today's file in `directory`. Returns the entry."""
    directory = Path(directory or LOGS_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    moment = (now or datetime.now(TIMEZONE)).astimezone(TIMEZONE)
    entry = {
        "id": str(uuid.uuid4()),
        "time": moment.isoformat(timespec="seconds"),
        "source": source,
        "transcript": transcript,
        "preset": preset,
        "score": None if score is None else round(score, 1),
        "result": result,
        "seconds": round(seconds, 2),
    }
    with open(directory / f"{moment:%Y-%m-%d}.jsonl", "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


MAX_ENTRIES_PER_DAY = 2000


def today(now=None):
    return (now or datetime.now(TIMEZONE)).astimezone(TIMEZONE).strftime("%Y-%m-%d")


def list_days(directory=None):
    """Days (YYYY-MM-DD, newest first) that have a log file."""
    directory = Path(directory or LOGS_DIR)
    if not directory.is_dir():
        return []
    return sorted((p.stem for p in directory.glob("*.jsonl") if _DAY_FILE.fullmatch(p.name)), reverse=True)


def read_day(day, directory=None):
    """Entries of one day, oldest first. `day` must be YYYY-MM-DD (it becomes part of a file name).

    Lines that are not a JSON object are skipped."""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        raise ValueError("day must be YYYY-MM-DD")
    path = Path(directory or LOGS_DIR) / f"{day}.jsonl"
    entries = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except FileNotFoundError:
        return []
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict):
            entries.append(entry)
    return entries[-MAX_ENTRIES_PER_DAY:]


def find_entry(entry_id, directory=None):
    """The entry with this id from any day on disk (newest day first), or None."""
    for day in list_days(directory):
        for entry in read_day(day, directory):
            if entry.get("id") == entry_id:
                return entry
    return None


def prune_daily_logs(directory=None, days=RETENTION_DAYS, now=None):
    """Delete logs/YYYY-MM-DD.jsonl files older than `days`. Returns how many.

    Age comes from the file name (Bangkok date). A file whose name is not one of ours is left alone.
    """
    directory = Path(directory or LOGS_DIR)
    if not directory.is_dir():
        return 0
    today = (now or datetime.now(TIMEZONE)).astimezone(TIMEZONE).date()
    cutoff = today - timedelta(days=days)
    removed = 0
    for path in directory.glob("*.jsonl"):
        if not _DAY_FILE.fullmatch(path.name):
            continue
        try:
            day = datetime.strptime(path.stem, "%Y-%m-%d").date()
        except ValueError:
            continue
        if day < cutoff:
            path.unlink(missing_ok=True)
            removed += 1
    return removed


def prune_command_files(directory=COMMANDS_DIR, days=RETENTION_DAYS, now=None):
    """Delete per-command files older than `days`. Returns how many.

    Age comes from the file name (local time). A file whose name is not one of ours is left alone.
    """
    directory = Path(directory)
    if not directory.is_dir():
        return 0
    cutoff = _aware(now or datetime.now().astimezone()) - timedelta(days=days)
    removed = 0
    for path in directory.glob("*.json"):
        try:
            when = _aware(datetime.strptime(path.stem[:19], _FILE_STAMP))
        except ValueError:
            continue
        if when < cutoff:
            path.unlink(missing_ok=True)
            removed += 1
    return removed


# ---- listen.log: stdout/stderr of the window-less `pythonw` process, one timestamp per line ----

def _stamp(now=None):
    return (now or datetime.now().astimezone()).isoformat(timespec="seconds")


class TimestampedWriter:
    """File-like wrapper: puts `[time] ` at the start of every non-empty line it writes, so the
    log can be pruned by age. Handles print() writing text and newline separately."""

    def __init__(self, f, clock=_stamp):
        self._f = f
        self._clock = clock
        self._at_line_start = True

    def write(self, text):
        out = []
        for part in text.splitlines(keepends=True):
            if self._at_line_start and part.strip("\r\n"):
                out.append(f"[{self._clock()}] ")
            out.append(part)
            self._at_line_start = part.endswith("\n")
        self._f.write("".join(out))
        return len(text)

    def flush(self):
        self._f.flush()

    def isatty(self):
        return False


def _aware(moment):
    return moment if moment.tzinfo else moment.astimezone()  # naive = local time


def _rewrite(path, lines):
    """Replace the file atomically: a crash never leaves a half-written log."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write("".join(line + "\n" for line in lines))
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def prune_commands(path=LOG_PATH, days=RETENTION_DAYS, now=None):
    """Remove entries older than `days` from the JSON-lines command log. Returns how many.

    A line that cannot be read as an entry is kept: it is not ours to delete.
    """
    path = Path(path)
    if not path.exists():
        return 0
    cutoff = _aware(now or datetime.now().astimezone()) - timedelta(days=days)
    kept, removed = [], 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            when = _aware(datetime.fromisoformat(json.loads(line)["time"]))
        except (ValueError, KeyError, TypeError):
            kept.append(line)
            continue
        if when >= cutoff:
            kept.append(line)
        else:
            removed += 1
    if removed:
        _rewrite(path, kept)
    return removed


def prune_text_log(path, days=RETENTION_DAYS, now=None):
    """Remove lines older than `days` from a `[time] text` log. Returns how many.

    A line without a readable timestamp has an unknown age, so it is removed too: that is the
    safe choice for a log that holds transcripts.
    """
    path = Path(path)
    if not path.exists():
        return 0
    cutoff = _aware(now or datetime.now().astimezone()) - timedelta(days=days)
    kept, removed = [], 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            if not line.startswith("["):
                raise ValueError
            when = _aware(datetime.fromisoformat(line[1 : line.index("]")]))
        except ValueError:
            removed += 1
            continue
        if when >= cutoff:
            kept.append(line)
        else:
            removed += 1
    if removed:
        _rewrite(path, kept)
    return removed
