"""The one object that owns Jarvis' state and its single worker thread.

States: off (master switch off) | idle | listening | transcribing | running.
Everything that touches the mic, Whisper or presets runs on the worker thread; the public commands
(`set_armed`, `toggle_listen`, `run_preset`) are thread-safe and return at once.

Speech only selects a preset by name: the transcript goes to the matcher and nowhere else.
"""
import queue
import threading
import time

from jarvis.audio import STOPPED, is_long_enough
from jarvis.presets import get_preset
from jarvis.vad import NO_SPEECH

OFF, IDLE, LISTENING, TRANSCRIBING, RUNNING = "off", "idle", "listening", "transcribing", "running"
SOURCES = ("hotkey", "web", "test")
HOTKEY_DEBOUNCE_SECONDS = 0.4  # a held key repeats; one press must toggle once
NO_SPEECH_REPLY = "ไม่ได้ยิน"
NO_MATCH_REPLY = "ไม่เข้าใจ"


class Engine:
    def __init__(self, presets, settings, *, record, transcribe, match, run_preset, spoken_reply,
                 speak, beep, log_command, hotkeys, build_prompt, log=print, clock=time.monotonic):
        self._presets = presets
        self._build_prompt = build_prompt
        self._prompt = build_prompt(presets)
        self._settings = settings
        self._record, self._transcribe, self._match = record, transcribe, match
        self._run_preset, self._spoken_reply = run_preset, spoken_reply
        self._speak, self._beep, self._log_command = speak, beep, log_command
        self._hotkeys = hotkeys
        self._log = log
        self._clock = clock
        self._lock = threading.RLock()
        self._armed = False
        self._phase = IDLE
        self._stop = threading.Event()
        self._last = None
        self._last_hotkey_at = None
        self._jobs = queue.Queue()
        self._worker = threading.Thread(target=self._work, name="jarvis-engine", daemon=True)
        self._worker.start()

    # ---- read ----

    @property
    def state(self):
        with self._lock:
            return OFF if not self._armed and self._phase == IDLE else self._phase

    @property
    def armed(self):
        return self._armed

    @property
    def settings(self):
        return self._settings

    @property
    def last(self):
        return self._last

    # ---- commands (any thread) ----

    def set_armed(self, armed):
        """Master switch. Off unregisters the hotkey and cancels a recording in progress."""
        with self._lock:
            self._armed = bool(armed)
            if not armed and self._phase == LISTENING:
                self._stop.set()
            self._apply_hotkey()

    def toggle_listen(self, source="web"):
        """idle -> start listening; listening -> stop now; busy or off -> ignored.

        Returns True if it did something."""
        if source not in SOURCES:
            raise ValueError(f"unknown source {source!r}")
        with self._lock:
            if source == "hotkey":  # key auto-repeat
                now = self._clock()
                if self._last_hotkey_at is not None and now - self._last_hotkey_at < HOTKEY_DEBOUNCE_SECONDS:
                    return False
                self._last_hotkey_at = now
            if not self._armed:
                return False
            if self._phase == LISTENING:
                self._stop.set()
                return True
            if self._phase != IDLE:
                return False
            self._phase = LISTENING
            self._stop.clear()
        self._jobs.put(("listen", source))
        return True

    def run_preset(self, name, source="test"):
        """Run a saved preset without speaking (the web's test button).

        True if started, False if busy; PresetError if there is no such preset."""
        if source not in SOURCES:
            raise ValueError(f"unknown source {source!r}")
        with self._lock:
            get_preset(self._presets, name)
            if self._phase != IDLE:
                return False
            self._phase = RUNNING
        self._jobs.put(("run", name, source))
        return True

    def update_settings(self, settings):
        """Apply new settings now; the hotkey is re-registered if it changed."""
        with self._lock:
            self._settings = settings
            self._apply_hotkey()

    def reload_presets(self, presets):
        """Swap in saved presets and rebuild Whisper's prompt, without a restart."""
        prompt = self._build_prompt(presets)
        with self._lock:
            self._presets, self._prompt = presets, prompt

    def wait_idle(self, timeout=5.0):
        """Block until nothing is queued or running (tests, shutdown). True if it got there."""
        deadline = self._clock() + timeout
        while self._clock() < deadline:
            with self._lock:
                if self._phase == IDLE and self._jobs.empty():
                    return True
            time.sleep(0.01)
        return False

    def close(self):
        with self._lock:
            self._armed = False
            self._stop.set()
            self._apply_hotkey()
        self._jobs.put(None)

    # ---- internals ----

    def _apply_hotkey(self):
        key = self._settings.hotkey if self._armed else None
        try:
            self._hotkeys.apply(key, lambda: self.toggle_listen("hotkey"))
        except Exception as e:  # a key the keyboard library rejects must not stop Jarvis
            self._log(f"could not register hotkey {key!r}: {e}")

    def _finish(self, entry):
        with self._lock:
            self._last = entry
            self._phase = IDLE

    def _record_result(self, source, transcript, preset, score, result, seconds):
        try:
            return self._log_command(source, transcript, preset, score, result, seconds)
        except OSError as e:
            self._log(f"could not write the log: {e}")
            return {"source": source, "transcript": transcript, "preset": preset,
                    "score": score, "result": result, "seconds": seconds}

    def _work(self):
        while True:
            job = self._jobs.get()
            if job is None:
                return
            source = job[-1]
            try:
                if job[0] == "listen":
                    self._do_listen(source)
                else:
                    self._do_run(job[1], source)
            except Exception as e:  # keep the worker alive; the browser never sees exception text
                self._log(f"command failed: {type(e).__name__}: {e}")
                self._finish(self._record_result(source, "", None, None, "error", 0.0))

    def _do_listen(self, source):
        started = self._clock()
        settings = self._settings
        if settings.beep:
            self._beep("start")  # blocks until it has played, so the beep is not recorded
        samples, outcome = self._record(self._stop, settings)
        if settings.beep:
            self._beep("stop")
        if not self._armed:  # switched off while listening: drop the clip
            self._finish(self._last)
            return
        if outcome == NO_SPEECH or (outcome == STOPPED and not is_long_enough(samples)):
            self._log(f"{NO_SPEECH_REPLY} ({outcome})")
            self._speak(NO_SPEECH_REPLY)
            self._finish(self._record_result(source, "", None, None, "no_speech", self._clock() - started))
            return
        with self._lock:
            self._phase = TRANSCRIBING
            presets, prompt = self._presets, self._prompt
        text, _ = self._transcribe(samples, prompt)
        name, score = self._match(text, presets, settings.match_threshold)
        if name is None:
            self._log(f"{NO_MATCH_REPLY}  (heard {text!r}, score {score:.0f})")
            self._speak(NO_MATCH_REPLY)
            self._finish(self._record_result(source, text, None, score, "no_match", self._clock() - started))
            return
        with self._lock:
            self._phase = RUNNING
        self._log(f"{name}  (heard {text!r}, score {score:.0f})")
        self._speak(self._spoken_reply(presets[name]))  # before the preset: it may wait/sleep
        failures = self._run_preset(presets, name, self._log)
        result = "error" if failures else "ok"
        self._finish(self._record_result(source, text, name, score, result, self._clock() - started))

    def _do_run(self, name, source):
        started = self._clock()
        failures = self._run_preset(self._presets, name, self._log)
        result = "error" if failures else "ok"
        self._finish(self._record_result(source, "", name, None, result, self._clock() - started))
