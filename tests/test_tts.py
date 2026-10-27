import threading
import time

from jarvis.tts import Speaker, find_voice


def make_voice(folder, name="th", with_config=True):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.onnx").write_bytes(b"x")
    if with_config:
        (folder / f"{name}.onnx.json").write_text("{}")


def recorder():
    calls = {"load": [], "synth": [], "play": [], "beep": 0, "log": []}

    def beep():
        calls["beep"] += 1

    return calls, dict(
        load=lambda m: calls["load"].append(m) or "voice",
        synthesize=lambda v, t: calls["synth"].append(t) or ("samples", 22050),
        play=lambda s, r: calls["play"].append((s, r)),
        beep=beep,
        log=calls["log"].append,
    )


def test_find_voice_needs_onnx_and_json(tmp_path):
    assert find_voice(tmp_path / "missing") is None
    make_voice(tmp_path, "a", with_config=False)
    assert find_voice(tmp_path) is None
    make_voice(tmp_path, "b")
    assert find_voice(tmp_path).name == "b.onnx"


def test_no_voice_beeps_and_does_not_crash(tmp_path):
    calls, hooks = recorder()
    s = Speaker(tmp_path / "voices", **hooks)
    s.speak("เปิดโหมดเกมแล้ว")
    s.wait()
    assert calls["beep"] == 1
    assert calls["load"] == [] and calls["play"] == []
    assert "no voice" in calls["log"][0]


def test_voice_speaks_and_loads_once(tmp_path):
    make_voice(tmp_path)
    calls, hooks = recorder()
    s = Speaker(tmp_path, **hooks)
    s.speak("หนึ่ง")
    s.speak("สอง")
    s.wait()
    assert len(calls["load"]) == 1
    assert sorted(calls["synth"]) == sorted(["หนึ่ง", "สอง"])
    assert len(calls["play"]) == 2 and calls["beep"] == 0


def test_load_failure_falls_back_to_beep(tmp_path):
    make_voice(tmp_path)
    calls, hooks = recorder()

    def bad_load(m):
        raise RuntimeError("corrupt")

    hooks["load"] = bad_load
    s = Speaker(tmp_path, **hooks)
    s.speak("x")
    s.wait()
    assert calls["beep"] == 1
    assert "could not load voice" in calls["log"][0]


def test_playback_failure_falls_back_to_beep(tmp_path):
    make_voice(tmp_path)
    calls, hooks = recorder()

    def bad_play(s, r):
        raise OSError("no audio device")

    hooks["play"] = bad_play
    s = Speaker(tmp_path, **hooks)
    s.speak("x")
    s.wait()
    assert calls["beep"] == 1


def test_speak_does_not_block_caller(tmp_path):
    make_voice(tmp_path)
    calls, hooks = recorder()
    release = threading.Event()
    hooks["play"] = lambda s, r: release.wait(5)
    sp = Speaker(tmp_path, **hooks)
    start = time.perf_counter()
    sp.speak("slow")
    assert time.perf_counter() - start < 0.5  # returned while playback is still "running"
    release.set()
    sp.wait()
