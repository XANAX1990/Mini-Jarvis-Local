# Jarvis

A small, fully local voice launcher for my Windows PC. I hold a key, say "เปิดโหมดเกม", and it opens my game setup (Discord, Chrome tabs, Roblox), then tells me it's done. No cloud, no account, and it runs on an old GTX 1060 3GB.

> **Status:** all six phases are built. The Piper voice file is not in the repo (see [Spoken replies](#spoken-replies)), and autostart is opt-in (`python -m jarvis autostart install`). See [`PLAN.md`](./PLAN.md) for the roadmap.

![Jarvis demo: `say`, then `listen` matching "เปิดโหมดเกม" to the game preset and ignoring a clip that is too short](GIF/Mini-Jarvis%20GIF.gif)

---

## Why

I was already launching my apps from `.bat` files. Jarvis is the next step: the same presets, triggered by voice, without sending my microphone to anyone's server.

## How it works

```
hold F9 → record mic → Whisper (local) → text
      → fuzzy-match against preset phrases → run preset → spoken reply (Piper)
```

- **No LLM in v1.** Commands are a short, known list, so fuzzy matching on the transcript is enough, and it tolerates small transcription mistakes. A small local LLM can be added later as a fallback for commands that don't match.
- **Presets are data, not code.** Everything Jarvis can do lives in `presets.json`. Speech can only pick a preset by name; it can never run arbitrary commands.
- **CPU first.** Whisper runs on the CPU with int8. GPU (GTX 1060, 3 GB) is an optional speed-up later.

## Features

| Feature | Status |
|---|---|
| Run presets from the command line (`python -m jarvis run game`) | ✅ Done |
| Push-to-talk recording (hold F9) | ✅ Done |
| Thai speech-to-text with faster-whisper (local; optional GPU) | ✅ Done |
| Fuzzy matching of speech to presets | ✅ Done |
| Spoken reply with Piper (Thai voice) | ✅ Done (beeps if no voice file is present) |
| Start automatically when I log in | ✅ Done (shortcut tested; not yet through a full log-out/in) |
| Ask "วันนี้ / อาทิตย์นี้ / เดือนนี้จ่ายไปเท่าไร" and hear the total from Slip Tracker (read only, on this PC) | ✅ Done |

## Presets

```json
{
  "game": {
    "phrases": ["เปิดโหมดเกม", "โหมดเล่นเกม"],
    "reply": "เปิดโหมดเกมแล้ว",
    "actions": [
      { "type": "run", "path": "%LocalAppData%\\Discord\\Update.exe", "args": ["--processStart", "Discord.exe"] },
      { "type": "uri", "target": "roblox:" },
      { "type": "wait", "seconds": 3 },
      { "type": "chrome", "urls": ["https://www.roblox.com/home"] }
    ]
  }
}
```

Action types: `run` (an exe with args), `open` (a file, folder or `.lnk` shortcut), `uri` (a protocol link like `discord:`), `chrome` (a new window with URLs), `wait`.
Chrome goes last on purpose: whatever opens last ends up in front.

## Tech stack

- Python 3.12 on Windows
- `sounddevice` + `numpy` (mic), `keyboard` (global hotkey)
- `faster-whisper` (speech-to-text, int8)
- `rapidfuzz` (matching)
- `piper-tts` (text-to-speech)
- `pytest`

## Getting started

```bat
git clone <repo-url> jarvis
cd jarvis
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m jarvis list
python -m jarvis run game
python -m jarvis listen
```

The first run of `listen` downloads the Whisper model (a few hundred MB) from Hugging Face: `Systran/faster-whisper-small` (MIT licence), which is what `faster-whisper` 1.2.1 uses for `small`. The revision checked on 2026-10-30 was `536b0662742c02347bc0e980a01041f333bce120` (last changed 2023-11-23); `WhisperModel` takes a `revision` argument if you ever want to pin it.

### Commands

| Command | What it does |
|---|---|
| `list` | Show presets and their trigger phrases |
| `run <name>` | Run a preset without voice |
| `record` | Hold F9, save `logs/last.wav`, print duration and peak level |
| `transcribe [files] [--model small] [--compare]` | Speech-to-text on WAV files, with timings |
| `say "<text>"` | Speak a sentence with the Piper voice (beeps if none) |
| `listen [--device cuda] [--threshold 70]` | The full loop: hold F9, speak, run the matching preset |
| `autostart install\|remove\|status` | Start `listen` at login (shortcut in the Startup folder) |

### Ask how much you spent

![Jarvis answering "เดือนนี้จ่ายไปเท่าไร" and "วันนี้จ่ายไปเท่าไร": each question picks its own period](GIF/spending.gif)

Say "เดือนนี้จ่ายไปเท่าไร" (also วันนี้ and อาทิตย์นี้) and Jarvis reads the total from the Slip Tracker API on this PC and says it in Thai, with the numbers as words. It only reads: Jarvis never changes anything in Slip Tracker. Setup: copy `.env.example` to `.env` and put Slip Tracker's `SLIPS_API_TOKEN` in it (the URL must be `127.0.0.1` or `localhost`; the token is never sent anywhere else). Start Slip Tracker first, or Jarvis answers "ระบบสลิปยังไม่เปิด". The plan is in `PLAN-spending.md`.

### Spoken replies

Download a Thai Piper voice (`.onnx` plus the `.onnx.json` with the same name) into `voices/`. Without one, Jarvis plays a short beep instead.

`voices/` is not pushed to GitHub: the model files are large and carry their own license.

### GPU (optional)

`python -m jarvis listen --device cuda` tries the GPU (int8). If the CUDA libraries are missing it falls back to the CPU and says so in the output.

### Start at login

```bat
python -m jarvis autostart install
```

This puts a shortcut in your Startup folder that runs `listen` with `pythonw` (no console window); output goes to `logs\listen.log`. It is a shortcut and not a Windows Service, because services can't open apps on your desktop. Undo with `autostart remove`.

## Project structure

```
jarvis/
├─ __main__.py      # CLI: list | run | record | transcribe | say | listen | autostart
├─ presets.py       # load + validate presets.json, run actions
├─ audio.py         # push-to-talk recording
├─ stt.py           # faster-whisper wrapper
├─ matcher.py       # transcript → preset (pure, tested)
├─ tts.py           # Piper wrapper
├─ log.py           # JSONL log of transcript, match, score
├─ autostart.py     # Startup-folder shortcut
└─ single.py        # one `listen` at a time (named mutex)
presets.json
voices/             # Piper voice files (.onnx + .onnx.json), not committed
logs/               # not committed
tests/
```

## Credits

- Thai voice: tranhuyluyen/piper-voices-thai (CC-BY-NC-4.0), non-commercial use only.
- Speech-to-text: Systran/faster-whisper-small (MIT), run with faster-whisper 1.2.1.

## License

MIT for the code. Voice and wake-word models keep their own licenses; some are non-commercial, which is fine for personal use.
