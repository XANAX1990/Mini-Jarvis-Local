import numpy as np

from jarvis.audio import (
    SAMPLE_RATE,
    duration_seconds,
    is_long_enough,
    load_wav,
    peak_level,
    save_wav,
)


def test_duration():
    assert duration_seconds(np.zeros(SAMPLE_RATE * 2)) == 2.0


def test_peak_level():
    assert peak_level(np.array([0.1, -0.5, 0.3], dtype=np.float32)) == 0.5
    assert peak_level(np.zeros(0)) == 0.0


def test_short_clips_ignored():
    assert not is_long_enough(np.zeros(int(SAMPLE_RATE * 0.29)))
    assert is_long_enough(np.zeros(int(SAMPLE_RATE * 0.3)))


def test_wav_roundtrip(tmp_path):
    samples = np.sin(np.linspace(0, 100, SAMPLE_RATE)).astype(np.float32) * 0.5
    path = tmp_path / "sub" / "clip.wav"
    save_wav(path, samples)
    loaded, rate = load_wav(path)
    assert rate == SAMPLE_RATE
    assert len(loaded) == len(samples)
    assert np.allclose(loaded, samples, atol=1e-3)


def test_save_clips_out_of_range(tmp_path):
    save_wav(tmp_path / "loud.wav", np.array([2.0, -2.0], dtype=np.float32))
    loaded, _ = load_wav(tmp_path / "loud.wav")
    assert peak_level(loaded) == 1.0
