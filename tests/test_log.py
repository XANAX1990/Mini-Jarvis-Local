import io
import json
import sys
from datetime import datetime, timedelta, timezone

import pytest

from jarvis import log
from jarvis.log import (
    RETENTION_DAYS,
    TimestampedWriter,
    log_command,
    prune_commands,
    prune_text_log,
)

NOW = datetime(2026, 10, 30, 12, 0, 0, tzinfo=timezone(timedelta(hours=7)))


def entry(days_old, transcript="x", tz=timezone(timedelta(hours=7))):
    when = (NOW - timedelta(days=days_old)).astimezone(tz)
    return json.dumps({"time": when.isoformat(timespec="seconds"), "transcript": transcript,
                       "preset": None, "score": 0, "seconds": 1}, ensure_ascii=False)


def write_lines(path, lines):
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_lines(path):
    return path.read_text(encoding="utf-8").splitlines()


def test_retention_is_thirty_days():
    assert RETENTION_DAYS == 30


# ---- commands.jsonl ----

def test_old_entries_are_removed_and_recent_ones_kept(tmp_path):
    p = tmp_path / "commands.jsonl"
    write_lines(p, [entry(31, "old"), entry(29, "recent"), entry(0, "today")])
    assert prune_commands(p, now=NOW) == 1
    kept = [json.loads(l)["transcript"] for l in read_lines(p)]
    assert kept == ["recent", "today"]


def test_exactly_thirty_days_old_is_still_kept(tmp_path):
    p = tmp_path / "commands.jsonl"
    write_lines(p, [entry(30, "edge"), entry(30.01, "just over")])
    assert prune_commands(p, now=NOW) == 1
    assert [json.loads(l)["transcript"] for l in read_lines(p)] == ["edge"]


def test_nothing_to_remove_leaves_the_file_untouched(tmp_path):
    p = tmp_path / "commands.jsonl"
    write_lines(p, [entry(1), entry(2)])
    before = p.read_bytes()
    assert prune_commands(p, now=NOW) == 0
    assert p.read_bytes() == before


def test_missing_file_is_fine(tmp_path):
    assert prune_commands(tmp_path / "nope.jsonl", now=NOW) == 0
    assert prune_text_log(tmp_path / "nope.log", now=NOW) == 0


def test_a_line_that_is_not_an_entry_is_kept_not_deleted(tmp_path):
    p = tmp_path / "commands.jsonl"
    write_lines(p, ["not json at all", '{"no_time": true}', entry(40, "old")])
    assert prune_commands(p, now=NOW) == 1
    assert read_lines(p) == ["not json at all", '{"no_time": true}']


def test_other_timezones_are_compared_correctly(tmp_path):
    p = tmp_path / "commands.jsonl"
    write_lines(p, [entry(31, "old-utc", tz=timezone.utc), entry(1, "new-utc", tz=timezone.utc)])
    assert prune_commands(p, now=NOW) == 1


def test_timestamps_without_an_offset_are_read_as_local_time(tmp_path):
    p = tmp_path / "commands.jsonl"
    old = (datetime.now() - timedelta(days=45)).isoformat(timespec="seconds")
    new = (datetime.now() - timedelta(days=1)).isoformat(timespec="seconds")
    write_lines(p, [json.dumps({"time": old}), json.dumps({"time": new})])
    assert prune_commands(p) == 1


def test_thai_transcripts_survive_the_rewrite(tmp_path):
    p = tmp_path / "commands.jsonl"
    write_lines(p, [entry(40, "เก่า"), entry(1, "เปิดโหมดเกม")])
    prune_commands(p, now=NOW)
    assert json.loads(read_lines(p)[0])["transcript"] == "เปิดโหมดเกม"


def test_no_temp_files_left_behind(tmp_path):
    p = tmp_path / "commands.jsonl"
    write_lines(p, [entry(40), entry(1)])
    prune_commands(p, now=NOW)
    assert [f.name for f in tmp_path.iterdir()] == ["commands.jsonl"]


def test_logging_then_pruning_with_real_clock(tmp_path):
    p = tmp_path / "commands.jsonl"
    log_command("เปิดโหมดเกม", "game", 100.0, 2.0, path=p)
    assert prune_commands(p) == 0  # an entry written just now is not old


# ---- listen.log ----

def test_writer_stamps_each_line_once_even_when_print_writes_in_pieces():
    buf = io.StringIO()
    w = TimestampedWriter(buf, clock=lambda: "T")
    print("loading models...", file=w)
    w.write("par")
    w.write("tial\n")
    print(file=w)  # empty line: not stamped
    assert buf.getvalue() == "[T] loading models...\n[T] partial\n\n"


def test_writer_is_a_usable_stream():
    w = TimestampedWriter(io.StringIO())
    assert w.isatty() is False
    w.flush()


def test_text_log_prune_by_timestamp(tmp_path):
    p = tmp_path / "listen.log"
    old = (NOW - timedelta(days=31)).isoformat(timespec="seconds")
    new = (NOW - timedelta(days=2)).isoformat(timespec="seconds")
    write_lines(p, [f"[{old}] heard 'old'", f"[{new}] heard 'new'"])
    assert prune_text_log(p, now=NOW) == 1
    assert read_lines(p) == [f"[{new}] heard 'new'"]


def test_text_log_lines_without_a_timestamp_are_removed(tmp_path):
    p = tmp_path / "listen.log"
    new = (NOW - timedelta(days=2)).isoformat(timespec="seconds")
    write_lines(p, ["heard 'from before timestamps existed'", "[garbage] x", f"[{new}] ok"])
    assert prune_text_log(p, now=NOW) == 2
    assert read_lines(p) == [f"[{new}] ok"]


def test_windowless_start_prunes_then_writes_stamped_lines(tmp_path, monkeypatch):
    from jarvis import __main__ as app

    commands = tmp_path / "logs" / "commands.jsonl"
    commands.parent.mkdir()
    old = (datetime.now().astimezone() - timedelta(days=45)).isoformat(timespec="seconds")
    (commands.parent / "listen.log").write_text(f"[{old}] heard 'old words'\n", encoding="utf-8")
    monkeypatch.setattr(log, "LOG_PATH", commands)
    monkeypatch.setattr(sys, "stdout", None)
    out = io.StringIO()
    monkeypatch.setattr(sys, "stderr", out)  # one stream present: only stdout is replaced
    app.redirect_output_if_windowless()
    print("Ready.")
    sys.stdout.flush()
    text = (commands.parent / "listen.log").read_text(encoding="utf-8")
    assert "old words" not in text  # pruned before the file was opened
    assert text.startswith("[") and text.rstrip().endswith("] Ready.")


def test_windowless_start_survives_a_log_that_cannot_be_replaced(tmp_path, monkeypatch):
    from jarvis import __main__ as app

    commands = tmp_path / "logs" / "commands.jsonl"
    commands.parent.mkdir()
    monkeypatch.setattr(log, "LOG_PATH", commands)

    def locked(*a, **k):
        raise PermissionError("another Jarvis has it open")

    monkeypatch.setattr(log, "prune_text_log", locked)
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", io.StringIO())
    app.redirect_output_if_windowless()  # must not raise
    print("still running")
    sys.stdout.flush()
    assert "still running" in (commands.parent / "listen.log").read_text(encoding="utf-8")
