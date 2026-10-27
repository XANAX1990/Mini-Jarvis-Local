"""Speech-to-text with faster-whisper, CPU int8, Thai.

The model is loaded once per size and reused.
"""
import time

from jarvis.audio import SAMPLE_RATE, load_wav

DEFAULT_MODEL = "small"
LANGUAGE = "th"

_models = {}


def build_prompt(presets):
    """Bias Whisper toward the command words: all preset phrases, space-separated."""
    return " ".join(p for preset in presets.values() for p in preset["phrases"])


def _load(size):
    from faster_whisper import WhisperModel

    return WhisperModel(size, device="cpu", compute_type="int8")


def get_model(size=DEFAULT_MODEL):
    if size not in _models:
        _models[size] = _load(size)
    return _models[size]


def transcribe(path, size=DEFAULT_MODEL, prompt=None):
    """Return (text, seconds). Seconds covers transcription only, not model loading."""
    # Decode the WAV ourselves: faster-whisper's own file decoding goes through
    # PyAV, whose newest versions break it.
    samples, rate = load_wav(path)
    if rate != SAMPLE_RATE:
        raise ValueError(f"{path}: expected {SAMPLE_RATE} Hz audio, got {rate} Hz")
    return transcribe_samples(samples, size, prompt)


def transcribe_samples(samples, size=DEFAULT_MODEL, prompt=None):
    """Like transcribe(), for 16 kHz mono float32 samples already in memory."""
    model = get_model(size)
    start = time.perf_counter()
    segments, _info = model.transcribe(
        samples, language=LANGUAGE, initial_prompt=prompt
    )
    text = "".join(s.text for s in segments).strip()  # generator: decoding happens here
    return text, time.perf_counter() - start
