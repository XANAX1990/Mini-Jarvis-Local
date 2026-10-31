"""Recording: starts when asked, stops by itself after silence (see vad.py) or when told to.

16 kHz mono float32 in memory, saved as 16-bit PCM WAV.
"""
import queue
import wave
from pathlib import Path

import numpy as np

from jarvis.vad import FRAME_SAMPLES, SAMPLE_RATE, EndpointDetector

MIN_SECONDS = 0.3
STOPPED = "stopped"  # recording result when the caller ended it early
LAST_WAV = Path(__file__).resolve().parent.parent / "logs" / "last.wav"


class AudioError(Exception):
    """No usable microphone, or recording failed."""


# --- pure helpers (no I/O besides the WAV file) ---

def duration_seconds(samples, rate=SAMPLE_RATE):
    return len(samples) / rate


def peak_level(samples):
    """Peak absolute amplitude, 0.0 (silence) to 1.0 (full scale)."""
    if len(samples) == 0:
        return 0.0
    return float(np.max(np.abs(samples)))


def is_long_enough(samples, rate=SAMPLE_RATE, minimum=MIN_SECONDS):
    return duration_seconds(samples, rate) >= minimum


def save_wav(path, samples, rate=SAMPLE_RATE):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())


def load_wav(path):
    with wave.open(str(path), "rb") as w:
        rate = w.getframerate()
        pcm = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
    return pcm.astype(np.float32) / 32767, rate


# --- recording (hardware) ---

def _check_microphone(sd):
    try:
        sd.query_devices(kind="input")
    except (ValueError, sd.PortAudioError):
        raise AudioError(
            "no microphone found - plug one in and set it as the default input device"
        ) from None


def record_until_silence(stop_event, settings):
    """Record from the default mic until the speaker stops, `stop_event` is set or the cap is hit.

    Returns (samples, outcome): outcome is a vad result (speech_done / no_speech / max_seconds)
    or STOPPED. Never listens beyond settings.max_seconds.
    """
    import sounddevice as sd

    _check_microphone(sd)
    frames = queue.Queue()
    detector = EndpointDetector(settings.silence_ms, settings.min_threshold, settings.max_seconds)
    chunks = []

    def on_audio(indata, frame_count, time_info, status):
        frames.put(indata[:, 0].copy())

    try:
        with sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="float32",
            blocksize=FRAME_SAMPLES, callback=on_audio,
        ):
            while True:
                if stop_event.is_set():
                    outcome = STOPPED
                    break
                try:
                    block = frames.get(timeout=0.05)
                except queue.Empty:
                    continue
                chunks.append(block)
                outcome = detector.feed(block)
                if outcome is not None:
                    break
    except sd.PortAudioError as e:
        raise AudioError(f"could not open the microphone: {e}") from None
    return (np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)), outcome


def beep(kind):
    """'start' (high, short) or 'stop' (lower). Blocks until played; 'start' also lets the speaker
    tail die out so the beep is not recorded."""
    import time
    import winsound

    if kind == "start":
        winsound.Beep(1200, 120)
        time.sleep(0.1)
    else:
        winsound.Beep(700, 120)
