"""Speech-to-text with faster-whisper, int8, Thai. CPU by default, GPU optional.

The model is loaded once per (size, device) and reused.
"""
import time

import numpy as np

from jarvis.audio import SAMPLE_RATE, load_wav

DEFAULT_MODEL = "small"
DEFAULT_DEVICE = "cpu"
LANGUAGE = "th"

_models = {}


def build_prompt(presets):
    """Bias Whisper toward the command words: all preset phrases, space-separated."""
    return " ".join(p for preset in presets.values() for p in preset["phrases"])


def _make(size, device):
    from faster_whisper import WhisperModel

    return WhisperModel(size, device=device, compute_type="int8")


def _warmup(model):
    """Run one tiny transcription. Missing CUDA libraries (cuBLAS/cuDNN) usually
    only fail here, on first use, not when the model is created."""
    segments, _ = model.transcribe(np.zeros(SAMPLE_RATE, dtype=np.float32), language=LANGUAGE)
    list(segments)


def _load(size, device=DEFAULT_DEVICE, log=print):
    if device == "cuda":
        try:
            model = _make(size, "cuda")
            _warmup(model)
            log(f"whisper '{size}' running on GPU (cuda, int8)")
            return model
        except Exception as e:  # missing CUDA libs / no GPU / out of memory
            log(f"CUDA unavailable ({e}); falling back to CPU")
    return _make(size, "cpu")


def get_model(size=DEFAULT_MODEL, device=DEFAULT_DEVICE):
    key = (size, device)
    if key not in _models:
        _models[key] = _load(size, device)
    return _models[key]


def transcribe(path, size=DEFAULT_MODEL, prompt=None, device=DEFAULT_DEVICE):
    """Return (text, seconds). Seconds covers transcription only, not model loading."""
    # Decode the WAV ourselves: faster-whisper's own file decoding goes through
    # PyAV, whose newest versions break it.
    samples, rate = load_wav(path)
    if rate != SAMPLE_RATE:
        raise ValueError(f"{path}: expected {SAMPLE_RATE} Hz audio, got {rate} Hz")
    return transcribe_samples(samples, size, prompt, device)


def transcribe_samples(samples, size=DEFAULT_MODEL, prompt=None, device=DEFAULT_DEVICE):
    """Like transcribe(), for 16 kHz mono float32 samples already in memory."""
    model = get_model(size, device)
    start = time.perf_counter()
    segments, _info = model.transcribe(
        samples, language=LANGUAGE, initial_prompt=prompt
    )
    text = "".join(s.text for s in segments).strip()  # generator: decoding happens here
    return text, time.perf_counter() - start
