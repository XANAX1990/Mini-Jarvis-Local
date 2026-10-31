# Lessons

<!-- Entry format: symptom / root cause / fix / rule -->

## 2026-10-29 · Whisper recites its prompt on non-speech and launches a preset
- **Symptom:** a preset launched when nobody gave a command. `commands.jsonl` had a transcript `โหมดเกม โหมดทำงาน โหมดทำงาน` (matched `game`). Reproduced offline: 3 s of silence gave `โหมดเล่น โหมด ทำงาน`, light noise gave `โหมดทำงาน โหมด` (matches `work`).
- **Root cause:** `initial_prompt` is built from every preset phrase to bias recognition. On silence or noise Whisper has nothing to decode and recites the prompt, and the recited phrases are exactly what the matcher looks for.
- **Fix (took two tries):** (1) first attempt: reject when the runner-up preset scores within 5 points of the best. Wrong: real commands share the word "โหมด", so a dropped-letter command (`เปิดโหมดงาน`, gap 3.3) was rejected while some recitals (gap 10) still passed. (2) `vad_filter=True` in `stt.transcribe_samples` drops non-speech before decoding (silence and noise now give an empty transcript; all 11 real speech clips transcribed the same). Backstop in `matcher.match`: a transcript containing full phrases of two different presets is rejected.
- **Rule:** Anything fed to Whisper as a prompt will come back as output on non-speech, so keep non-speech away from the decoder (VAD) and don't let prompt text alone trigger an action. Measure the score gaps of real commands before choosing a margin rule.

## 2026-10-29 · Two `listen` copies after autostart (pythonw has no window)
- **Symptom:** the same command logged 3 times within 2 seconds, each taking 7-9 s to transcribe (normally ~2 s).
- **Root cause:** `pythonw` shows no console, so starting the shortcut again looks like nothing happened. Several copies listened to the same F9 and ran every preset more than once.
- **Fix:** `jarvis/single.py` takes a Windows named mutex at the start of `listen`; a second copy prints a message to `logs/listen.log` and exits with code 1. The OS frees the mutex when the process dies, so there is no stale lock file.
- **Rule:** A background app with no window needs a single-instance guard and a log file. Don't kill by image name (`taskkill /IM pythonw.exe`) when testing: it takes down every copy; stop only the PIDs you started.

## 2026-10-31 · Jarvis transcribed its own spoken reply
- **Symptom:** the log had a line with transcript `ไม่ได้ยิน` (Jarvis' own reply for "didn't hear you"), result `no_match`, score 37.5.
- **Root cause:** replies are spoken in a background thread (`Speaker.speak` returns at once). With tap-to-talk the next tap can come while the reply is still playing, so the mic recorded the speaker.
- **Fix:** the engine calls `wait_speaking` (`Speaker.wait`) before the start beep, so recording only begins when nothing is playing.
- **Rule:** anything that plays sound must finish before the mic opens; test the mic path with a reply still playing, not only with silence.

## 2026-10-31 · A phrase added from the log broke the commands it was meant to help
- **Symptom:** after "เพิ่มเป็นวลี" on `เปิดโหมดเกม และเปิดโหมดทำงาน` (and a similar line for `work`), saying the same thing did nothing, and even the plain `เปิดโหมดเกม`, `โหมดเกม` and `โหมดทำงาน` stopped working. The log showed `no_match` with score 100.
- **Root cause:** the API only refused exact duplicates and warned on near-duplicates. The matcher refuses to guess when a transcript holds full phrases of two presets, or is a fragment of phrases of two presets. A phrase containing another preset's phrase therefore can never match, and as a fragment-of-two it made the existing commands ambiguous too.
- **Fix:** before saving, run the real matcher on the resulting presets (`matcher.unmatched_phrases`). A save that stops a phrase of another preset from matching is refused (422, naming the phrase and preset); a phrase added from the log must match; in the editor a phrase that cannot match is a warning.
- **Rule:** validate a saved phrase by asking the matcher, not by string rules, and compare before/after so a save can never break a command that worked. Tests that read the live `presets.json` (`test_spending_phrases`) caught it first: keep them.

## 2026-11-01 · A test run migrated the owner's real presets.json
- **Symptom:** after wiring a one-time migration into `main()`, `programs.json` appeared in the project folder and `presets.json` had `run` steps without a `path`, though only the test suite had been run.
- **Root cause:** two tests called `main(["list"])` and only stubbed some of the startup helpers (`ensure_presets_file`, `load_presets`). The new `migrate_legacy_runs` and `ensure_programs_file` still ran against the real files in the project folder.
- **Fix:** `tests/conftest.py` has an autouse fixture that stubs every startup helper for every test, and a session fixture that fails the run if `presets.json`, `programs.json` or `settings.json` changed while the tests ran.
- **Rule:** a function that writes the owner's files must never be reachable from a test without an explicit temp path. Whenever a new startup step touches a real file, add it to the autouse stub in the same commit, and run the suite once with the real files copied aside.
