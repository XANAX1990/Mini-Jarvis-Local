"""Append one JSON line per command to logs/commands.jsonl."""
import json
from datetime import datetime
from pathlib import Path

LOG_PATH = Path(__file__).resolve().parent.parent / "logs" / "commands.jsonl"


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
