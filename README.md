# Jarvis

A small, fully local voice launcher for my Windows PC. I hold a key, say "เปิดโหมดเกม", and it opens my game setup (Discord, Chrome tabs, Roblox), then tells me it's done. No cloud, no account, and it runs on an old GTX 1060 3GB.

> **Status:** in development. See [`PLAN.md`](./PLAN.md) for the roadmap and current progress.

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
| Run presets from the command line (`python -m jarvis run game`) | ⏳ Planned |
| Push-to-talk recording (hold F9) | ⏳ Planned |
| Thai speech-to-text with faster-whisper (local) | ⏳ Planned |
| Fuzzy matching of speech to presets | ⏳ Planned |
| Spoken reply with Piper (Thai voice) | ⏳ Planned |
| Start automatically when I log in | ⏳ Planned |

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

## Project structure

```
jarvis/
├─ __main__.py      # CLI: list | run <preset> | listen
├─ presets.py       # load + validate presets.json, run actions
├─ audio.py         # push-to-talk recording
├─ stt.py           # faster-whisper wrapper
├─ matcher.py       # transcript → preset (pure, tested)
├─ tts.py           # Piper wrapper
└─ log.py           # JSONL log of transcript, match, score
presets.json
voices/             # Piper voice files (.onnx + .onnx.json), not committed
logs/               # not committed
tests/
```

## License

MIT for the code. Voice and wake-word models keep their own licenses; some are non-commercial, which is fine for personal use.
