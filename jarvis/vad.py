"""End-of-speech detector on 30 ms frames. Pure: no I/O, no clock.

Energy based. The noise floor is the average level of the first 300 ms; the threshold is
`max(min_threshold, noise * 2.5)`. Speech starts after 3 loud frames in a row and ends after
`silence_ms` of quiet. If nobody speaks within 5 s the recording is cancelled, and `max_seconds`
is a hard cap.
"""
import numpy as np

SAMPLE_RATE = 16_000
FRAME_MS = 30
FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000
CALIBRATION_FRAMES = 10  # 300 ms
START_FRAMES = 3  # loud frames in a row that count as speech starting
NOISE_FACTOR = 2.5
NO_SPEECH_SECONDS = 5

SPEECH_DONE = "speech_done"
NO_SPEECH = "no_speech"
MAX_SECONDS = "max_seconds"


def frame_level(frame):
    """RMS level of one frame, 0.0 (silence) to 1.0 (full scale)."""
    return float(np.sqrt(np.mean(np.square(frame, dtype=np.float64))))


class EndpointDetector:
    def __init__(self, silence_ms=1000, min_threshold=0.01, max_seconds=15):
        self.silence_frames = max(1, -(-silence_ms // FRAME_MS))  # ceil
        self.min_threshold = min_threshold
        self.max_frames = int(max_seconds * 1000 // FRAME_MS)
        self.no_speech_frames = NO_SPEECH_SECONDS * 1000 // FRAME_MS
        self.threshold = None  # known once the first 300 ms are measured
        self.result = None
        self.frames = 0  # complete frames processed so far
        self.speech_started_at = None  # frame index where the 3rd loud frame in a row landed
        self._pending = np.zeros(0, dtype=np.float32)
        self._calibration = []
        self._loud_run = 0
        self._quiet_run = 0

    def feed(self, samples):
        """Add audio of any length. Returns the result once it is decided, else None."""
        if self.result is not None:
            return self.result
        data = np.concatenate([self._pending, np.asarray(samples, dtype=np.float32)])
        whole = len(data) // FRAME_SAMPLES * FRAME_SAMPLES
        self._pending = data[whole:]
        for start in range(0, whole, FRAME_SAMPLES):
            self._frame(data[start : start + FRAME_SAMPLES])
            if self.result is not None:
                break
        return self.result

    def _frame(self, frame):
        level = frame_level(frame)
        self.frames += 1
        if self.threshold is None:
            self._calibration.append(level)
            if len(self._calibration) == CALIBRATION_FRAMES:
                noise = sum(self._calibration) / CALIBRATION_FRAMES
                self.threshold = max(self.min_threshold, noise * NOISE_FACTOR)
        else:
            loud = level > self.threshold
            if self.speech_started_at is None:
                self._loud_run = self._loud_run + 1 if loud else 0
                if self._loud_run >= START_FRAMES:
                    self.speech_started_at = self.frames
            else:
                self._quiet_run = 0 if loud else self._quiet_run + 1
                if self._quiet_run >= self.silence_frames:
                    self.result = SPEECH_DONE
                    return
        if self.speech_started_at is None and self.frames >= self.no_speech_frames:
            self.result = NO_SPEECH
        elif self.frames >= self.max_frames:
            self.result = MAX_SECONDS


def analyze(samples, **kwargs):
    """Run a whole clip through the detector: (result or None, frames used)."""
    detector = EndpointDetector(**kwargs)
    result = detector.feed(samples)
    return result, detector.frames


def analyze_levels(samples, min_threshold=0.01):
    """Levels of a mic-test clip, so a person can see whether auto-stop will work in their room.

    Uses the same rules as the detector: the noise floor is the first 300 ms, the threshold is
    max(min_threshold, noise x 2.5), speech is 3 loud frames in a row after that."""
    samples = np.asarray(samples, dtype=np.float32)
    count = len(samples) // FRAME_SAMPLES
    levels = [frame_level(samples[i * FRAME_SAMPLES : (i + 1) * FRAME_SAMPLES]) for i in range(count)]
    if len(levels) <= CALIBRATION_FRAMES:
        return {"peak": 0.0, "level": 0.0, "noise": 0.0, "threshold": min_threshold, "detects_speech": False}
    noise = sum(levels[:CALIBRATION_FRAMES]) / CALIBRATION_FRAMES
    threshold = max(min_threshold, noise * NOISE_FACTOR)
    run = longest = 0
    for level in levels[CALIBRATION_FRAMES:]:
        run = run + 1 if level > threshold else 0
        longest = max(longest, run)
    return {
        "peak": round(float(np.max(np.abs(samples))), 4),
        "level": round(max(levels), 4),  # the loudest 30 ms frame
        "noise": round(noise, 4),
        "threshold": round(threshold, 4),
        "detects_speech": longest >= START_FRAMES,
    }
