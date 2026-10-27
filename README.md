# Jarvis

A small, fully local voice launcher for my Windows PC. I hold a key, say "เปิดโหมดเกม", and it opens my game setup (Discord, Chrome tabs, Roblox), then tells me it's done. No cloud, no account, and it runs on an old GTX 1060 3GB.

> **Status:** all six phases are built. Spoken replies need a Piper voice file in `voices/`, and autostart is opt-in (`python -m jarvis autostart install`). See [`PLAN.md`](./PLAN.md) for the roadmap.

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
| Spoken reply with Piper (Thai voice) | 🟡 Built, needs a voice file; beeps without one |
| Start automatically when I log in | 🟡 Built, not yet tried across a real login |

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

The first run of `listen` downloads the Whisper model (a few hundred MB).

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

### Spoken replies

Download a Thai Piper voice (`.onnx` plus the `.onnx.json` with the same name) into `voices/`. Without one, Jarvis plays a short beep instead.

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
└─ autostart.py     # Startup-folder shortcut
presets.json
voices/             # Piper voice files (.onnx + .onnx.json), not committed
logs/               # not committed
tests/
```

## License

MIT for the code. Voice and wake-word models keep their own licenses; some are non-commercial, which is fine for personal use.
