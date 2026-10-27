"""Push-to-talk recording: hold F9 to record, release to stop.

16 kHz mono float32 in memory, saved as 16-bit PCM WAV.
"""
import time
import wave
from pathlib import Path

import numpy as np

SAMPLE_RATE = 16_000
MIN_SECONDS = 0.3
HOTKEY = "f9"
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


def record_once():
    """Block until F9 is held and released; return the samples (maybe too short)."""
    import keyboard
    import sounddevice as sd

    _check_microphone(sd)
    chunks = []

    def on_audio(indata, frames, time_info, status):
        chunks.append(indata[:, 0].copy())

    keyboard.wait(HOTKEY)  # returns when F9 is pressed
    try:
        with sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="float32", callback=on_audio
        ):
            while keyboard.is_pressed(HOTKEY):
                time.sleep(0.01)
    except sd.PortAudioError as e:
        raise AudioError(f"could not open the microphone: {e}") from None
    return np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)


def record_clip():
    """Keep waiting until a clip at least MIN_SECONDS long is recorded."""
    while True:
        samples = record_once()
        if is_long_enough(samples):
            return samples
        print(f"ignored: clip under {MIN_SECONDS}s")
