import argparse

import pytest

from jarvis.__main__ import build_parser, threshold_arg
from jarvis.matcher import DEFAULT_THRESHOLD, MIN_THRESHOLD, match, normalize

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


def test_recited_prompt_with_phrases_of_two_presets_is_rejected():
    # What Whisper produced on non-speech: it recited the prompt phrases.
    name, score = match("โหมดเล่นเกม โหมดทำงาน โหมดทำงาน", PRESETS)
    assert name is None
    assert score == 100  # would have matched without the rule


def test_one_preset_phrase_repeated_still_matches():
    assert match("โหมดทำงาน โหมดทำงาน", PRESETS)[0] == "work"


def test_real_commands_still_win_though_presets_share_a_word():
    # "โหมด" is shared by both presets, so the runner-up scores ~84; must still win.
    for text, expected in [
        ("เปิดโหมดเกม", "game"),
        ("เปิดโหมดทำงาน", "work"),
        ("เปิดโหมดเกน", "game"),
        ("นีโน เปิดโหมดเล่นเกม", "game"),
        ("นีโน เปิดโหมดทำงาน", "work"),
    ]:
        assert match(text, PRESETS)[0] == expected


def test_empty_transcript_no_match():
    assert match("", PRESETS) == (None, 0.0)
    assert match("  ... ", PRESETS) == (None, 0.0)


def test_threshold_is_configurable():
    transcript = "เปิดโหมดเกมส์"
    assert match(transcript, PRESETS, threshold=101)[0] is None
    assert match(transcript, PRESETS, threshold=0)[0] == "game"


# ---- the command line cannot switch the threshold off (SECURITY.md: never guess a preset) ----

def test_default_threshold_is_unchanged():
    from jarvis.settings import Settings

    assert build_parser().parse_args(["listen"]).threshold is None  # then settings.json decides
    assert Settings().match_threshold == DEFAULT_THRESHOLD == 70


@pytest.mark.parametrize("value", ["50", "70", "99.5", "100"])
def test_thresholds_in_range_are_accepted(value):
    assert build_parser().parse_args(["listen", "--threshold", value]).threshold == float(value)


@pytest.mark.parametrize("value", ["0", "-5", "49.9", "30", "100.1", "101", "abc", "", "nan", "inf", "-inf"])
def test_thresholds_that_would_make_jarvis_guess_are_refused(value, capsys):
    with pytest.raises(SystemExit):
        build_parser().parse_args(["listen", "--threshold", value])
    assert "--threshold" in capsys.readouterr().err


def test_error_message_explains_the_floor():
    with pytest.raises(argparse.ArgumentTypeError, match=str(MIN_THRESHOLD)):
        threshold_arg("10")


def test_match_itself_stays_flexible_for_tests_and_tools():
    assert match("เปิดโหมดเกม", PRESETS, threshold=0)[0] == "game"


# ---- phrases that would not match back to their own preset ----

def test_unmatched_phrases_is_empty_for_a_clean_set():
    from jarvis.matcher import unmatched_phrases

    assert unmatched_phrases(PRESETS) == set()


def test_unmatched_phrases_finds_phrases_that_overlap_another_preset():
    import copy

    from jarvis.matcher import unmatched_phrases

    presets = copy.deepcopy(PRESETS)
    presets["game"]["phrases"].append("เปิดโหมดเกม และเปิดโหมดทำงาน")
    presets["work"]["phrases"].append("เปิดโหมดเกม โหมดทำงาน")
    bad = unmatched_phrases(presets)
    assert ("game", "เปิดโหมดเกม และเปิดโหมดทำงาน") in bad and ("work", "เปิดโหมดเกม โหมดทำงาน") in bad
    assert ("game", "เปิดโหมดเกม") in bad  # the plain command broke as well
