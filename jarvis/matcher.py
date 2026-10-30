"""Transcript -> preset name. Pure: no I/O.

Speech can only ever *select* a preset by name; nothing here builds a command.
"""
import unicodedata

from rapidfuzz import fuzz

DEFAULT_THRESHOLD = 70
MIN_THRESHOLD = 50  # the CLI refuses anything lower: below this Jarvis would be guessing a preset
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
    scores = {}  # preset name -> best score over its phrases
    for name, preset in presets.items():
        for phrase in preset["phrases"]:
            phrase = normalize(phrase)
            # partial_ratio scores any fragment of the phrase as 100 ("โหมด",
            # "เปิด"), so a transcript far shorter than the phrase can't match it.
            if len(heard) < MIN_COVERAGE * len(phrase):
                continue
            scores[name] = max(scores.get(name, 0.0), fuzz.partial_ratio(heard, phrase))
    if not scores:
        return None, 0.0
    best_name, best_score = max(scores.items(), key=lambda item: item[1])
    if best_score < threshold:
        return None, best_score
    # A transcript holding full phrases of two different presets is Whisper reciting
    # its prompt ("โหมดเกม โหมดทำงาน"), not a command. Don't guess which to launch.
    named = [
        name
        for name, preset in presets.items()
        if any(normalize(p) in heard for p in preset["phrases"])
    ]
    if len(named) > 1:
        return None, best_score
    return best_name, best_score
