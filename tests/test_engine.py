import threading

import numpy as np
import pytest

from jarvis.audio import STOPPED
from jarvis.engine import Engine
from jarvis.presets import PresetError
from jarvis.settings import Settings
from jarvis.vad import NO_SPEECH, SPEECH_DONE

PRESETS = {"game": {"phrases": ["เปิดโหมดเกม"], "reply": "เปิดโหมดเกมแล้ว", "actions": []}}
CLIP = np.ones(16_000, dtype=np.float32)  # 1 s: long enough


class FakeHotkeys:
    def __init__(self):
        self.calls = []
        self.callback = None

    def apply(self, key, callback):
        self.calls.append(key)
        self.callback = callback


class Rig:
    """An Engine whose mic, Whisper and speakers are fakes the test controls."""

    def __init__(self, outcome=SPEECH_DONE, samples=CLIP, text="เปิดโหมดเกม", score=100.0,
                 match_name="game", settings=None, failures=0):
        self.events = []
        self.logged = []
        self.spoken = []
        self.hotkeys = FakeHotkeys()
        self.recording = threading.Event()  # set once the fake mic is open
        self.release = threading.Event()  # the fake mic returns when this is set (or on stop)
        self.hold_mic = False
        self.outcome, self.samples, self.text, self.score = outcome, samples, text, score
        self.match_name, self.failures = match_name, failures
        self.engine = Engine(
            PRESETS,
            settings or Settings(),
            record=self.record,
            transcribe=self.transcribe,
            match=lambda text, presets, threshold: (self.match_name, self.score),
            run_preset=self.run_preset,
            spoken_reply=lambda preset: preset["reply"],
            speak=self.spoken.append,
            beep=lambda kind: self.events.append(f"beep-{kind}"),
            log_command=self.log_command,
            hotkeys=self.hotkeys,
            build_prompt=lambda presets: " ".join(p for v in presets.values() for p in v["phrases"]),
            log=lambda *_: None,
        )

    def record(self, stop_event, settings):
        self.events.append("record")
        self.recording.set()
        if self.hold_mic:
            while not (stop_event.is_set() or self.release.is_set()):
                stop_event.wait(0.01)
            if stop_event.is_set():
                return self.samples, STOPPED
        return self.samples, self.outcome

    def transcribe(self, samples, prompt):
        self.events.append("transcribe")
        self.prompt = prompt
        return self.text, 0.5

    def run_preset(self, presets, name, log=print):
        self.events.append(f"run-{name}")
        return self.failures

    def log_command(self, source, transcript, preset, score, result, seconds):
        entry = {"source": source, "transcript": transcript, "preset": preset, "score": score,
                 "result": result}
        self.logged.append(entry)
        return entry

    def tap(self, source="hotkey"):
        return self.engine.toggle_listen(source)


@pytest.fixture
def rig():
    r = Rig()
    yield r
    r.engine.close()


def test_starts_off_until_armed(rig):
    assert rig.engine.state == "off"
    rig.engine.set_armed(True)
    assert rig.engine.state == "idle"


def test_toggle_is_ignored_while_off(rig):
    assert rig.tap() is False
    assert rig.engine.wait_idle()
    assert rig.events == [] and rig.logged == []


def test_full_command_beeps_around_the_recording_then_runs_the_preset(rig):
    rig.engine.set_armed(True)
    assert rig.tap() is True
    assert rig.engine.wait_idle()
    assert rig.events == ["beep-start", "record", "beep-stop", "transcribe", "run-game"]
    assert rig.spoken == ["เปิดโหมดเกมแล้ว"]
    assert rig.logged == [{"source": "hotkey", "transcript": "เปิดโหมดเกม", "preset": "game",
                           "score": 100.0, "result": "ok"}]
    assert rig.engine.last == rig.logged[0]
    assert rig.engine.state == "idle"
    assert rig.prompt == "เปิดโหมดเกม"


def test_beeps_can_be_turned_off():
    r = Rig(settings=Settings(beep=False))
    r.engine.set_armed(True)
    r.tap()
    assert r.engine.wait_idle()
    assert "beep-start" not in r.events and "beep-stop" not in r.events
    r.engine.close()


def test_no_speech_logs_no_speech_and_runs_nothing():
    r = Rig(outcome=NO_SPEECH, samples=np.zeros(16_000, dtype=np.float32))
    r.engine.set_armed(True)
    r.tap("web")
    assert r.engine.wait_idle()
    assert "transcribe" not in r.events and "run-game" not in r.events
    assert [(e["source"], e["result"]) for e in r.logged] == [("web", "no_speech")]
    assert r.spoken == ["ไม่ได้ยิน"]
    r.engine.close()


def test_no_match_says_so_and_runs_nothing():
    r = Rig(match_name=None, score=40.0, text="อะไรสักอย่าง")
    r.engine.set_armed(True)
    r.tap()
    assert r.engine.wait_idle()
    assert "run-game" not in r.events
    assert r.logged[0]["result"] == "no_match" and r.logged[0]["transcript"] == "อะไรสักอย่าง"
    assert r.spoken == ["ไม่เข้าใจ"]
    r.engine.close()


def test_a_failing_action_is_logged_as_error():
    r = Rig(failures=1)
    r.engine.set_armed(True)
    r.tap()
    assert r.engine.wait_idle()
    assert r.logged[0]["result"] == "error"
    r.engine.close()


def test_second_tap_while_listening_stops_early(rig):
    rig.hold_mic = True
    rig.engine.set_armed(True)
    rig.tap()
    assert rig.recording.wait(2)
    assert rig.engine.state == "listening"
    assert rig.tap("web") is True  # stop now
    assert rig.engine.wait_idle()
    assert rig.events[-2:] == ["transcribe", "run-game"]  # the clip so far is still used


def test_early_stop_with_a_tiny_clip_is_no_speech():
    r = Rig(samples=np.zeros(100, dtype=np.float32))
    r.hold_mic = True
    r.engine.set_armed(True)
    r.tap()
    assert r.recording.wait(2)
    r.tap("web")
    assert r.engine.wait_idle()
    assert r.logged[0]["result"] == "no_speech"
    r.engine.close()


def test_state_goes_through_transcribing_and_running():
    seen = []
    r = Rig()
    r.transcribe = lambda samples, prompt: (seen.append(r.engine.state), ("เปิดโหมดเกม", 0.1))[1]
    r.run_preset = lambda presets, name, log=print: seen.append(r.engine.state) or 0
    r.engine._transcribe, r.engine._run_preset = r.transcribe, r.run_preset
    r.engine.set_armed(True)
    r.tap()
    assert r.engine.wait_idle()
    assert seen == ["transcribing", "running"]
    r.engine.close()


def test_toggle_is_ignored_while_transcribing():
    gate = threading.Event()
    r = Rig()
    started = threading.Event()

    def slow(samples, prompt):
        started.set()
        gate.wait(2)
        return "เปิดโหมดเกม", 0.1

    r.engine._transcribe = slow
    r.engine.set_armed(True)
    r.tap()
    assert started.wait(2)
    assert r.engine.state == "transcribing"
    assert r.tap("web") is False
    gate.set()
    assert r.engine.wait_idle()
    assert r.events.count("record") == 1
    r.engine.close()


def test_toggle_is_ignored_while_running():
    gate = threading.Event()
    started = threading.Event()
    r = Rig()

    def slow(presets, name, log=print):
        started.set()
        gate.wait(2)
        return 0

    r.engine._run_preset = slow
    r.engine.set_armed(True)
    r.tap()
    assert started.wait(2)
    assert r.engine.state == "running"
    assert r.tap("web") is False
    gate.set()
    assert r.engine.wait_idle()
    r.engine.close()


def test_switching_off_while_listening_drops_the_clip():
    r = Rig()
    r.hold_mic = True
    r.engine.set_armed(True)
    r.tap()
    assert r.recording.wait(2)
    r.engine.set_armed(False)
    assert r.engine.wait_idle()
    assert "transcribe" not in r.events and r.logged == []
    assert r.engine.state == "off"
    r.engine.close()


def test_master_switch_registers_and_unregisters_the_hotkey(rig):
    rig.engine.set_armed(True)
    rig.engine.set_armed(False)
    assert rig.hotkeys.calls == ["caps lock", None]


def test_changing_the_hotkey_re_registers_it(rig):
    rig.engine.set_armed(True)
    rig.engine.update_settings(Settings(hotkey="right ctrl"))
    assert rig.hotkeys.calls[-1] == "right ctrl"
    rig.engine.update_settings(Settings(hotkey="right ctrl", beep=False))
    assert rig.hotkeys.calls[-1] == "right ctrl"  # same key: the Hotkeys object keeps its registration


def test_hotkey_callback_toggles_and_key_repeat_is_ignored():
    now = [100.0]
    r = Rig()
    r.engine._clock = lambda: now[0]
    r.engine.set_armed(True)
    r.hotkeys.callback()
    now[0] += 0.05  # auto-repeat
    r.hotkeys.callback()
    assert r.engine.wait_idle()
    assert r.events.count("record") == 1
    now[0] += 1.0
    r.hotkeys.callback()
    assert r.engine.wait_idle()
    assert r.events.count("record") == 2
    r.engine.close()


def test_test_run_runs_the_preset_without_speaking_and_logs_source_test(rig):
    assert rig.engine.state == "off"
    assert rig.engine.run_preset("game") is True  # allowed while the master switch is off
    assert rig.engine.wait_idle()
    assert rig.events == ["run-game"] and rig.spoken == []
    assert (rig.logged[0]["source"], rig.logged[0]["preset"], rig.logged[0]["result"]) == ("test", "game", "ok")


def test_test_run_of_an_unknown_preset_is_an_error(rig):
    with pytest.raises(PresetError):
        rig.engine.run_preset("nope")
    assert rig.events == []


def test_test_run_is_refused_while_busy(rig):
    rig.hold_mic = True
    rig.engine.set_armed(True)
    rig.tap()
    assert rig.recording.wait(2)
    assert rig.engine.run_preset("game") is False
    rig.release.set()
    assert rig.engine.wait_idle()


def test_unknown_source_is_rejected(rig):
    with pytest.raises(ValueError):
        rig.engine.toggle_listen("telepathy")


def test_reload_presets_changes_what_is_matched_and_prompted(rig):
    rig.engine.reload_presets({"work": {"phrases": ["เปิดโหมดงาน"], "reply": "x", "actions": []}})
    rig.engine.set_armed(True)
    rig.tap()
    assert rig.engine.wait_idle()
    assert rig.prompt == "เปิดโหมดงาน"


def test_an_exception_in_the_worker_is_logged_as_error_and_the_engine_keeps_working():
    r = Rig()
    calls = []

    def flaky(stop_event, settings):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("mic exploded at C:\\secret\\path")
        return CLIP, SPEECH_DONE

    r.engine._record = flaky
    r.engine.set_armed(True)
    r.tap()
    assert r.engine.wait_idle()
    assert r.logged[0]["result"] == "error"
    assert "secret" not in repr(r.logged[0])
    r.tap("web")
    assert r.engine.wait_idle()
    assert r.logged[-1]["result"] == "ok"
    r.engine.close()


def test_a_hotkey_the_keyboard_library_rejects_does_not_crash_jarvis():
    class Rejecting(FakeHotkeys):
        def apply(self, key, callback):
            raise ValueError("unknown key")

    r = Rig()
    r.engine._hotkeys = Rejecting()
    r.engine.set_armed(True)  # logs, does not raise
    assert r.engine.state == "idle"
    r.engine.close()
