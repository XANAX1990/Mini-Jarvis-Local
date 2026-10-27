"""Spoken replies with Piper. Never raises: any problem falls back to a beep.

Speaking runs in a daemon thread so the next command is not blocked.
"""
import threading
from pathlib import Path

import numpy as np

VOICES_DIR = Path(__file__).resolve().parent.parent / "voices"
NO_MATCH_REPLY = "ไม่เข้าใจ"


def find_voice(voices_dir=VOICES_DIR):
    """First .onnx model that has its .onnx.json config beside it, else None."""
    voices_dir = Path(voices_dir)
    if not voices_dir.is_dir():
        return None
    for model in sorted(voices_dir.glob("*.onnx")):
        if model.with_name(model.name + ".json").is_file():
            return model
    return None


def _load_piper(model_path):
    from piper import PiperVoice

    return PiperVoice.load(model_path)


def _synthesize(voice, text):
    chunks = list(voice.synthesize(text))
    rate = chunks[0].sample_rate
    return np.concatenate([c.audio_float_array for c in chunks]), rate


def _play(samples, rate):
    import sounddevice as sd

    sd.stop()  # cut any reply still playing
    sd.play(samples, rate)
    sd.wait()


def _beep():
    import winsound

    winsound.Beep(880, 150)


class Speaker:
    def __init__(
        self,
        voices_dir=VOICES_DIR,
        load=_load_piper,
        synthesize=_synthesize,
        play=_play,
        beep=_beep,
        log=print,
    ):
        self._voices_dir = voices_dir
        self._load, self._synthesize, self._play, self._beep = load, synthesize, play, beep
        self._log = log
        self._voice = None
        self._voice_checked = False
        self._lock = threading.Lock()
        self._threads = []

    def _get_voice(self):
        """Load the voice once; None (and a log line) if unavailable."""
        if not self._voice_checked:
            self._voice_checked = True
            model = find_voice(self._voices_dir)
            if model is None:
                self._log(f"no voice in {self._voices_dir} - using a beep instead")
            else:
                try:
                    self._voice = self._load(model)
                except Exception as e:  # corrupt/unsupported model: degrade, don't crash
                    self._log(f"could not load voice {model.name}: {e} - using a beep")
        return self._voice

    def warm(self):
        """Load the voice now so the first reply isn't delayed."""
        with self._lock:
            self._get_voice()

    def _say(self, text):
        with self._lock:
            voice = self._get_voice()
            try:
                if voice is None:
                    self._beep()
                else:
                    self._play(*self._synthesize(voice, text))
            except Exception as e:
                self._log(f"speech failed: {e}")
                try:
                    self._beep()
                except Exception:
                    pass

    def speak(self, text):
        """Return immediately; the reply plays in the background."""
        t = threading.Thread(target=self._say, args=(text,), daemon=True)
        self._threads = [x for x in self._threads if x.is_alive()] + [t]
        t.start()

    def wait(self, timeout=None):
        """Block until queued replies finish (used by tests and one-shot commands)."""
        for t in list(self._threads):
            t.join(timeout)
