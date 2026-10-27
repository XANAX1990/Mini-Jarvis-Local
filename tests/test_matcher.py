import json

from jarvis.log import log_command
from jarvis.matcher import DEFAULT_THRESHOLD, match, normalize

PRESETS = {
    "game": {"phrases": ["เปิดโหมดเกม", "โหมดเล่นเกม"]},
    "work": {"phrases": ["เปิดโหมดทำงาน", "โหมดทำงาน"]},
}


def test_normalize_drops_spaces_and_punctuation_keeps_thai_marks():
    assert normalize("  เปิด โหมด, เกม! ") == "เปิดโหมดเกม"
    assert normalize("Hello, World 2") == "helloworld2"


def test_exact_phrase():
    assert match("เปิดโหมดเกม", PRESETS) == ("game", 100.0)
    assert match("เปิดโหมดทำงาน", PRESETS)[0] == "work"


def test_phrase_with_spaces_and_punctuation():
    assert match("เปิด โหมด เกม.", PRESETS)[0] == "game"


def test_phrase_with_typo():
    name, score = match("เปิดโหมดเกน", PRESETS)  # last letter misheard
    assert name == "game"
    assert DEFAULT_THRESHOLD <= score < 100

    name, score = match("เปิดโหมดงาน", PRESETS)  # dropped letters
    assert name == "work"
    assert DEFAULT_THRESHOLD <= score < 100


def test_short_fragments_do_not_match():
    for fragment in ("โหมด", "เปิด", "เกม", "ทำงาน"):
        assert match(fragment, PRESETS)[0] is None


def test_unrelated_sentence_no_match():
    name, score = match("วันนี้อากาศดีมากเลย ไปกินข้าวกัน", PRESETS)
    assert name is None
    assert score < DEFAULT_THRESHOLD


def test_empty_transcript_no_match():
    assert match("", PRESETS) == (None, 0.0)
    assert match("  ... ", PRESETS) == (None, 0.0)


def test_threshold_is_configurable():
    transcript = "เปิดโหมดเกมส์"
    assert match(transcript, PRESETS, threshold=101)[0] is None
    assert match(transcript, PRESETS, threshold=0)[0] == "game"


def test_log_writes_one_json_line_per_command(tmp_path):
    path = tmp_path / "logs" / "commands.jsonl"
    log_command("เปิดโหมดเกม", "game", 100.0, 2.345, path=path)
    log_command("ไม่รู้เรื่อง", None, 41.23, 1.0, path=path)
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    first, second = (json.loads(line) for line in lines)
    assert first["transcript"] == "เปิดโหมดเกม"
    assert first["preset"] == "game"
    assert first["score"] == 100.0
    assert first["seconds"] == 2.35
    assert second["preset"] is None
    assert {"time", "transcript", "preset", "score", "seconds"} <= set(first)
