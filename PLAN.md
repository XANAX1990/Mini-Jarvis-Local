# Jarvis: Implementation Plan

## Working agreement (for Claude Code)

- Do **one phase at a time**. Stop at the end of each phase, tell me exactly what to run to verify it, and wait for "ok" before the next one.
- **Commit after each phase** (`feat(phase-N): ...`).
- Target: **Windows 10/11, Python 3.12**, GTX 1060 3 GB. Everything runs locally; no network calls except downloading models the first time.
- Checks at the end of every phase: `pytest` passes and `python -m jarvis --help` runs.
- **Scope is fixed.** No LLM, no GUI/tray app, no cloud APIs, no wake word, no GPU work until the phase that says so. If something seems needed, ask first.
- **Safety rule:** speech only ever selects a preset name. Never build a shell command from transcript text, and never use `shell=True` with anything that came from audio.
- Pure logic (`matcher.py`, preset validation) has no I/O and is unit tested.
- When a bug takes more than one try to fix, add an entry to `LESSONS.md` (symptom / root cause / fix / rule).

---

## Phase 1: Project + preset runner (no voice)

- [x] Project layout as in README, `requirements.txt`, `.gitignore` (`.venv/`, `voices/`, `logs/`, `models/`)
- [x] `presets.json` with 2 presets: `game` (Discord, Roblox, Chrome with roblox.com + instagram) and `work` (TODO: ask me)
- [x] Validate presets on load (unknown action type, missing fields → clear error)
- [x] Actions: `run` (expand `%VARS%`, `subprocess.Popen([path, *args])`), `open` (`os.startfile`), `uri` (`os.startfile`), `chrome` (`--new-window` + URLs), `wait`
- [x] CLI: `python -m jarvis list`, `python -m jarvis run <name>`
- [x] Tests: preset validation, unknown preset name

**Verify:** `python -m jarvis run game` opens Discord, Roblox and a Chrome window in front.

## Phase 2: Push-to-talk recording

- [x] `audio.py`: hold **F9** to record from the default mic, release to stop; 16 kHz mono; ignore clips under 0.3 s
- [x] `python -m jarvis record` saves `logs/last.wav` and prints duration + peak level
- [x] Clear error if no microphone is found

**Verify:** record "เปิดโหมดเกม", play `logs/last.wav`, voice is clear.

## Phase 3: Speech-to-text (CPU)

- [x] `stt.py`: faster-whisper, `device="cpu"`, `compute_type="int8"`, `language="th"`, model loaded **once** and reused
- [x] Pass the preset phrases as `initial_prompt` so Whisper leans toward my command words
- [x] `python -m jarvis transcribe logs/last.wav` prints text + seconds taken
- [x] Model size configurable (`small` default); print a comparison of `small` vs `medium` on the same 5 recordings

**Verify:** 5 recordings of my commands; I check how many come out readable and how long each takes.

## Phase 4: Matching + the full loop

- [x] `matcher.py`: normalize (lowercase, remove spaces/punctuation, Thai has no word spaces), score each preset phrase with `rapidfuzz.fuzz.partial_ratio`, return best preset + score
- [x] Threshold (start at 70, configurable): below it → no match
- [x] Tests: exact phrase, phrase with a typo, unrelated sentence → no match
- [x] `python -m jarvis listen`: loop forever — hold F9 → record → transcribe → match → run preset (or print "ไม่เข้าใจ")
- [x] `log.py`: append one JSON line per command: time, transcript, preset, score, seconds

**Verify:** say each preset's phrase 5 times; it runs the right one; random speech runs nothing.

## Phase 5: Spoken reply

- [x] `tts.py`: Piper with a Thai voice from `voices/` (I'll download the `.onnx` + `.onnx.json`); speak the preset's `reply`, or "ไม่เข้าใจ" on no match
- [x] If no voice file is found → play a short system beep instead (don't crash)
- [x] Speaking must not block the next command for long (run it in a thread)

**Verify:** "เปิดโหมดเกม" → apps open and I hear "เปิดโหมดเกมแล้ว".

## Phase 6: Daily use

- [x] Autostart: a shortcut in the user's **Startup folder** that runs `listen` with `pythonw` (no console window). Not a Windows Service: services can't open apps on my desktop.
- [x] Optional GPU: try `device="cuda"`, `compute_type="int8"` (GTX 1060 is compute 6.1); if CUDA libs are missing, fall back to CPU automatically and say so in the log
- [x] README: tick features, add a short demo GIF

**Verify:** log out and in → Jarvis is listening without me starting it.

---

## Later (not in scope now)

- Wake word ("hey jarvis", openWakeWord; non-commercial license is fine for personal use)
- Small local LLM (1–4B) only as a fallback when fuzzy matching fails
- More action types (close apps, volume, focus mode)

## What I have to do myself

| When | What |
|---|---|
| Before Phase 1 | Install Python 3.12 with "Add to PATH" |
| Phase 1 | Tell Claude Code what the `work` preset should open |
| Phase 2 | Make sure a mic is plugged in and set as default |
| Phase 5 | Download a Thai Piper voice (`.onnx` + `.onnx.json`) into `voices/` |
