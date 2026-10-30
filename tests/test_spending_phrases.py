"""Phase 2: the three spending questions differ by one word, so they must not be confused
with each other, with a bare "how much?", or with the game/work commands."""
import pytest

from jarvis.matcher import match
from jarvis.presets import load_presets
from jarvis.stt import build_prompt

PRESETS = load_presets()  # the real presets.json


@pytest.mark.parametrize(
    "preset", ["spending-today", "spending-week", "spending-month"]
)
def test_every_phrase_of_every_spending_preset_selects_that_preset(preset):
    for phrase in PRESETS[preset]["phrases"]:
        assert match(phrase, PRESETS)[0] == preset, phrase


def test_the_two_ways_of_saying_week_both_work():
    assert match("สัปดาห์นี้ใช้ไปเท่าไร", PRESETS)[0] == "spending-week"
    assert match("อาทิตย์นี้ใช้ไปเท่าไร", PRESETS)[0] == "spending-week"


@pytest.mark.parametrize(
    "heard,expected",
    [
        ("เดือนนี้จ่ายไปเท่าไหร่", "spending-month"),   # spelled the other way
        ("วันนี้จ่ายไปเท่าไหร่", "spending-today"),
        ("อาทิตย์นี้จ่ายไปเท่าไหร่", "spending-week"),
        ("วันนี้ จ่ายไป เท่าไร", "spending-today"),     # spaces from Whisper
        ("เดือนนี้ใช้ไปเท่าไร.", "spending-month"),
    ],
)
def test_small_spelling_differences_still_pick_the_right_period(heard, expected):
    assert match(heard, PRESETS)[0] == expected


@pytest.mark.parametrize(
    "heard",
    [
        "จ่ายไปเท่าไร",        # which period?
        "ใช้ไปเท่าไร",
        "นี้จ่ายไปเท่าไร",     # the period word was lost
        "เท่าไร",
        "เดือนนี้",             # no question
        "วันนี้อากาศเป็นยังไง",
    ],
)
def test_a_question_without_a_clear_period_is_not_answered(heard):
    assert match(heard, PRESETS)[0] is None, heard


def test_whisper_reciting_its_prompt_is_not_a_command():
    heard = "วันนี้จ่ายไปเท่าไร อาทิตย์นี้จ่ายไปเท่าไร เดือนนี้จ่ายไปเท่าไร"
    assert match(heard, PRESETS)[0] is None


def test_phrases_that_are_nearly_the_same_cannot_be_told_apart_so_neither_is_guessed():
    presets = {
        "a": {"phrases": ["วันนี้จ่ายไปเท่าไร"]},
        "b": {"phrases": ["วันนี้จ่ายไปเท่าไห"]},  # one letter different
    }
    assert match("วันนี้จ่ายไปเท่าไห", presets)[0] is None
    assert match("วันนี้จ่ายไปเท่าไร", presets)[0] is None


def test_a_clear_winner_is_not_affected_by_the_margin():
    presets = {
        "a": {"phrases": ["วันนี้จ่ายไปเท่าไร"]},
        "b": {"phrases": ["เปิดโหมดเกม"]},
    }
    assert match("วันนี้จ่ายไปเท่าไร", presets) == ("a", 100.0)


def test_game_and_work_commands_still_work_next_to_the_spending_phrases():
    assert match("เปิดโหมดเกม", PRESETS)[0] == "game"
    assert match("โหมดทำงาน", PRESETS)[0] == "work"
    assert match("เปิดโหมดงาน", PRESETS)[0] == "work"  # dropped letters, as before


def test_game_and_work_phrases_are_not_taken_for_spending():
    for phrase in ("เปิดโหมดเกม", "เปิดโหมดทำงาน", "โหมดเล่นเกม"):
        assert not match(phrase, PRESETS)[0].startswith("spending")


def test_all_spending_phrases_are_in_whispers_prompt():
    prompt = build_prompt(PRESETS)
    for name in ("spending-today", "spending-week", "spending-month"):
        for phrase in PRESETS[name]["phrases"]:
            assert phrase in prompt
