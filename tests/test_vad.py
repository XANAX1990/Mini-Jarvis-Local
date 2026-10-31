import numpy as np

from jarvis.vad import (
    FRAME_SAMPLES,
    MAX_SECONDS,
    NO_SPEECH,
    SPEECH_DONE,
    EndpointDetector,
    analyze,
    analyze_levels,
)


def quiet(frames, level=0.002):
    return np.full(frames * FRAME_SAMPLES, level, dtype=np.float32)


def loud(frames, level=0.2):
    return np.full(frames * FRAME_SAMPLES, level, dtype=np.float32)


def test_silence_only_is_no_speech_after_five_seconds():
    result, frames = analyze(quiet(300))
    assert result == NO_SPEECH
    assert frames == 166  # 5 s of 30 ms frames


def test_speech_then_silence_stops_one_second_after_it_ends():
    # 0.3 s calibration, 0.6 s of speech, then silence
    clip = np.concatenate([quiet(10), loud(20), quiet(100)])
    result, frames = analyze(clip, silence_ms=1000)
    assert result == SPEECH_DONE
    assert frames == 10 + 20 + 34  # ceil(1000 / 30) quiet frames


def test_a_shorter_pause_does_not_stop_it():
    clip = np.concatenate([quiet(10), loud(10), quiet(30), loud(10), quiet(100)])
    result, frames = analyze(clip, silence_ms=1000)
    assert result == SPEECH_DONE
    assert frames == 10 + 10 + 30 + 10 + 34


def test_two_loud_frames_are_not_speech():
    clip = np.concatenate([quiet(10), loud(2), quiet(300)])
    assert analyze(clip)[0] == NO_SPEECH


def test_endless_speech_level_noise_hits_the_cap():
    clip = np.concatenate([quiet(10), loud(100000)])
    result, frames = analyze(clip, max_seconds=15)
    assert result == MAX_SECONDS
    assert frames == 500


def test_steady_noise_is_not_speech():
    # the threshold is 2.5 x the measured floor, so constant noise never crosses it
    result, _ = analyze(quiet(400, level=0.05))
    assert result == NO_SPEECH


def test_threshold_has_a_floor_for_very_quiet_rooms():
    d = EndpointDetector(min_threshold=0.01)
    d.feed(quiet(10, level=0.0001))
    assert d.threshold == 0.01


def test_threshold_follows_the_noise_floor():
    d = EndpointDetector(min_threshold=0.01)
    d.feed(quiet(10, level=0.04))
    assert abs(d.threshold - 0.1) < 1e-6


def test_audio_can_arrive_in_odd_sized_chunks():
    clip = np.concatenate([quiet(10), loud(20), quiet(100)])
    d = EndpointDetector()
    result = None
    for start in range(0, len(clip), 700):
        result = d.feed(clip[start : start + 700])
        if result:
            break
    assert result == SPEECH_DONE
    assert d.frames == 64


def test_result_is_final():
    d = EndpointDetector()
    d.feed(quiet(300))
    assert d.feed(loud(50)) == NO_SPEECH


def test_levels_of_a_quiet_room_with_speech():
    levels = analyze_levels(np.concatenate([quiet(10, 0.004), loud(10, 0.2)]), min_threshold=0.01)
    assert levels["noise"] == 0.004 and levels["threshold"] == 0.01
    assert levels["level"] == 0.2 and levels["peak"] == 0.2
    assert levels["detects_speech"] is True


def test_levels_when_nobody_speaks():
    levels = analyze_levels(quiet(60, 0.003))
    assert levels["detects_speech"] is False and levels["level"] < levels["threshold"]


def test_levels_in_a_noisy_room_raise_the_threshold():
    levels = analyze_levels(quiet(60, 0.08), min_threshold=0.01)
    assert abs(levels["threshold"] - 0.2) < 1e-6 and levels["detects_speech"] is False


def test_two_loud_frames_are_not_enough_in_a_mic_test_either():
    assert analyze_levels(np.concatenate([quiet(10), loud(2), quiet(30)]))["detects_speech"] is False


def test_levels_of_a_clip_shorter_than_the_calibration():
    assert analyze_levels(quiet(5))["detects_speech"] is False
    assert analyze_levels(np.zeros(0))["peak"] == 0.0
