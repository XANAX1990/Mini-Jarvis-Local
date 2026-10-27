"""Transcript -> preset name. Pure: no I/O.

Speech can only ever *select* a preset by name; nothing here builds a command.
"""
import unicodedata

from rapidfuzz import fuzz

DEFAULT_THRESHOLD = 70
MIN_COVERAGE = 0.6  # transcript must be at least this fraction of the phrase's length


def normalize(text):
    """Lowercase and keep only letters, digits and combining marks.

    Thai has no word spaces, and its vowels/tone marks are combining marks
    (category M*), so they must be kept while spaces and punctuation go.
    """
    return "".join(
        c for c in text.lower() if unicodedata.category(c)[0] in ("L", "N", "M")
    )


def match(transcript, presets, threshold=DEFAULT_THRESHOLD):
    """Return (preset_name or None, best_score).

    The score is the best partial_ratio over every phrase of every preset.
    Below `threshold` there is no match, but the best score is still returned.
    """
    heard = normalize(transcript)
    if not heard:
        return None, 0.0
    best_name, best_score = None, 0.0
    for name, preset in presets.items():
        for phrase in preset["phrases"]:
            phrase = normalize(phrase)
            # partial_ratio scores any fragment of the phrase as 100 ("โหมด",
            # "เปิด"), so a transcript far shorter than the phrase can't match it.
            if len(heard) < MIN_COVERAGE * len(phrase):
                continue
            score = fuzz.partial_ratio(heard, phrase)
            if score > best_score:
                best_name, best_score = name, score
    if best_score < threshold:
        return None, best_score
    return best_name, best_score
