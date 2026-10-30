"""Append one JSON line per command to logs/commands.jsonl, and keep logs for a limited time.

Transcripts are what people said near the microphone, so they are not kept for ever:
`prune_commands()` (when `listen` starts) and `prune_text_log()` (before listen.log is opened) drop
everything older than RETENTION_DAYS from logs/commands.jsonl and logs/listen.log. logs/ is never committed (see .gitignore).
"""
import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

LOG_PATH = Path(__file__).resolve().parent.parent / "logs" / "commands.jsonl"
RETENTION_DAYS = 30


def log_command(transcript, preset, score, seconds, path=LOG_PATH):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "time": datetime.now().astimezone().isoformat(timespec="seconds"),
        "transcript": transcript,
        "preset": preset,
        "score": round(score, 1),
        "seconds": round(seconds, 2),
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


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
