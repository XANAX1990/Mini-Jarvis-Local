# Jarvis Web: Plan (add-on to mini-jarvis)

A local web app for Jarvis: click (or tap one key) to talk instead of holding F9, manage presets without editing JSON, and see what Jarvis did today.
Put this file in the `mini-jarvis` repo next to `PLAN.md`. Phases continue from the existing ones (Phase 7 onwards).

## Decisions (already made, don't re-ask)

| Topic | Decision |
|---|---|
| Talk mode | Press once → beep → listening → **stops by itself after ~1 s of silence** → beep. Pressing again while listening stops early. |
| Hotkey | Default **Caps Lock** (one key, easy on a 60% keyboard), suppressed so it doesn't toggle caps. Changeable in Settings. Plain letters, digits and typing keys (space, enter, tab, backspace, esc, left/right shift) are **refused** as a single-key hotkey: they would fire while typing, or vanish from typing if suppressed. They're allowed with a modifier (e.g. `ctrl+alt+j`). |
| Master switch | "Jarvis ฟังอยู่ / ปิด" toggle on the home page. Off → the hotkey is unregistered (the key works normally again) and the mic button is disabled. |
| Web stack | Next.js (App Router, TypeScript, Tailwind) built as a **static export** (`output: 'export'`) into `web/out/`. The Jarvis Python process serves those files and the API on **one port: `127.0.0.1:3003`**. One process, no Node at runtime, no console window. |
| Dev mode | `next dev -p 3004` for the web; the Python API allows CORS from `http://localhost:3004` **only** when `JARVIS_DEV=1`. |
| Live status | Web polls `GET /api/state` every 500 ms (simple and enough on localhost). |
| Presets UI | Phrases as **tags** (type + Enter, × to remove). Actions as an ordered list: type dropdown + fields + move up/down + delete. A "ทดสอบ" button runs the preset without speaking. |
| Logs | One JSONL file per day: `logs/YYYY-MM-DD.jsonl`. Files older than **30 days** are deleted at startup. |
| Language | UI text in Thai. Code, comments, commit messages in English. |

## Working agreement (for Claude Code)

- **Read the existing code first** (`jarvis/*.py`, `presets.json`, `tests/`) and reuse it: the matcher, preset runner, STT and TTS stay; this work wraps them, it doesn't rewrite them.
- One phase at a time. Stop, tell me exactly what to run to verify, wait for "ok". Commit after each phase (`feat(phase-N): ...`).
- Checks every phase: `pytest` passes, `python -m jarvis --help` runs; from Phase 9, `npm run build` in `web/` passes with no type errors.
- Follow `SECURITY.md` (the **Local web API** section is new and matters: this API can start programs).
- Keep all existing rules: speech only selects a preset by name; no `shell=True`; no LLM; runs as my normal user.
- **Scope is fixed.** No accounts/login, no remote access, no wake word, no mobile layout work beyond "doesn't break", no charts. If something seems needed, ask first.
- When a bug takes more than one try, add it to `LESSONS.md`.
- Target: Windows 11, Python 3.12 (`py -3.12`), Node LTS.

---

## Phase 7: Engine: toggle + auto-stop + master switch

- [x] `engine.py`: one object that owns the state and a single worker thread. States: `off` (master switch off) · `idle` · `listening` · `transcribing` · `running`. Thread-safe commands: `set_armed(bool)`, `toggle_listen(source)`, `run_preset(name, source="test")`. Everything that touches the mic, Whisper or presets goes through it.
- [x] Toggle rules: `idle` + toggle → `listening`; `listening` + toggle → stop now; `transcribing`/`running` + toggle → ignored; `off` → ignored.
- [x] `vad.py` (pure, no I/O): energy-based end-of-speech detector on 30 ms frames. Noise floor measured from the first 300 ms; threshold = `max(min_threshold, noise × 2.5)`; speech starts after 3 loud frames in a row; stop after `silence_ms` (default 1000) of quiet once speech has started; no speech within 5 s → cancel with result `no_speech`; hard cap `max_seconds` (default 15).
- [x] Start recording **after** the start beep has finished (so the beep isn't recorded). Beeps with `winsound.Beep` (start: high and short, stop: lower), can be turned off in settings.
- [x] `settings.py`: `settings.json` (ignored by git) with defaults; `settings.example.json` committed. Keys: `hotkey` ("caps lock"), `armed_on_start` (true), `silence_ms`, `min_threshold`, `max_seconds`, `beep` (true), `match_threshold` (existing value). Validated on load; invalid → defaults + a log line.
- [x] Hotkey: `keyboard.add_hotkey(hotkey, ..., suppress=True)`; re-registered on change; unregistered when the master switch is off. Validation rule from **Decisions** in one pure function, unit tested.
- [x] F9 hold mode is removed (the new key replaces it).
- [x] Log: switch `log.py` to daily files with fields `id` (uuid4), `time` (ISO, Asia/Bangkok), `source` (`hotkey | web | test`), `transcript`, `preset`, `score`, `result` (`ok | no_match | no_speech | error`), `seconds`. Retention: delete `logs/*.jsonl` older than 30 days at startup. Old log file: leave it, don't migrate.
- [x] Tests: VAD on synthetic arrays (silence only → no_speech; speech then silence → stops at the right frame; endless noise → cap), state transitions, hotkey validation, retention picks the right files.

**Verify:** `python -m jarvis listen` → tap Caps Lock → beep → say "เปิดโหมดเกม" → it stops by itself about 1 s after I finish → beep → preset runs. Tap and say nothing → after 5 s "ไม่ได้ยิน" (or a beep) and a `no_speech` line in today's log. Caps Lock light doesn't change.

## Phase 8: Local API (inside the Jarvis process)

- [x] FastAPI app started by `listen` in a background thread with uvicorn on `127.0.0.1:3003` (`--no-web` flag to skip). If the port is taken → "Jarvis is already running" and exit.
- [x] Security middleware (details in `SECURITY.md`): Host allow-list, Origin check and `X-Jarvis: 1` header on every non-GET, JSON only, no CORS except dev mode.
- [x] Endpoints:
  - `GET /api/state` → `{ armed, state, hotkey, last: { time, transcript, preset, score, result } }`
  - `POST /api/armed` `{ armed }`
  - `POST /api/listen/toggle`
  - `GET /api/presets` · `POST /api/presets` · `PUT /api/presets/{name}` · `DELETE /api/presets/{name}` · `POST /api/presets/{name}/test`
  - `GET /api/action-types` → the list of action types and their fields (the web builds the editor from this, so a new type like `spending` later needs no web change)
  - `GET /api/logs?date=YYYY-MM-DD` (default today) · `GET /api/logs/dates` (days that have a log)
  - `POST /api/logs/{id}/add-phrase` `{ preset }` → adds that line's transcript to the preset's phrases
  - `GET /api/settings` · `PUT /api/settings`
  - `POST /api/hotkey/capture` → waits up to 10 s for the next key combo (`keyboard.read_hotkey`), returns its name, doesn't save it
- [x] Presets: one set of pydantic models used for both the file and the API. Save = validate → write `presets.json.tmp` → `os.replace` (atomic) → keep the previous file as `presets.json.bak` → engine reloads presets and rebuilds Whisper's `initial_prompt`. Preset names: `^[a-z0-9-]{1,32}$`.
- [x] Validation: the same phrase (after the matcher's normalization) in two presets → 422 with which preset has it. Very similar phrases across presets (rapidfuzz ≥ 90) → saved, but the response includes a warning.
- [x] Errors to the browser: short message + field name, no stack traces or file paths.
- [x] Tests with `TestClient`: each endpoint; wrong Host → 403; POST without `X-Jarvis` → 403; foreign Origin → 403; invalid preset → 422 and `presets.json` unchanged; save → matcher finds the new phrase without restart; add-phrase from a log line.

**Verify:** with Jarvis running, `curl.exe http://127.0.0.1:3003/api/state` returns JSON; a POST without the header is refused; `pytest` passes.

## Phase 9: Web: scaffold + home page

- [x] `web/`: Next.js App Router + TypeScript + Tailwind, `output: 'export'`, `trailingSlash: true`, `images.unoptimized: true`. API base: same origin in production, `http://127.0.0.1:3003` in dev (`NEXT_PUBLIC_API_BASE`).
- [x] One small `api.ts` client that always sends `Content-Type: application/json` and `X-Jarvis: 1`.
- [x] Layout: top nav (หน้าหลัก · Presets · Log · ตั้งค่า), a status dot in the nav that's visible on every page.
- [x] Home `/`:
  - Big round mic button. Colors and labels by state: `off` gray "ปิดอยู่" (disabled) · `idle` green "กดเพื่อพูด" · `listening` red pulsing "กำลังฟัง… (กดเพื่อหยุด)" · `transcribing` amber "กำลังแปลงเสียง" · `running` blue "กำลังทำ: <preset>"
  - Master switch "Jarvis ฟังอยู่" on/off
  - Hint line: "หรือกดปุ่ม <hotkey>"
  - Last command card: what it heard, which preset, score, result
  - Today's last 5 log lines + link to Log
- [x] If the API isn't reachable → a clear banner "Jarvis ไม่ได้เปิดอยู่" instead of a broken page.
- [x] Python serves `web/out/` at `/` (static files, `index.html` fallback per folder). If `web/out/` doesn't exist → `/` shows "run `npm run build` in web/".

**Verify:** `npm run build` → restart Jarvis → open `http://127.0.0.1:3003` → click the mic, speak, watch the states change and the preset run; press Caps Lock and see the same on the page; switch off → Caps Lock types caps again.

## Phase 10: Web: presets

- [x] `/presets`: list of preset cards (name, phrases as tags, number of steps), "+ เพิ่ม preset".
- [x] Editor (side panel or `/presets/edit/?name=...`; no dynamic routes, static export): name, phrases as tags (Enter or comma adds, × removes, duplicates ignored), reply, steps list built from `/api/action-types`:
  - เปิดโปรแกรม (`run`): exe path + args (tags)
  - เปิดไฟล์/โฟลเดอร์/shortcut (`open`): path
  - ลิงก์แอป (`uri`): e.g. `discord:`
  - Chrome (`chrome`): URLs (tags)
  - รอ (`wait`): seconds
- [x] Each step: move up/down, delete. Under path fields, a hint: "Shift + คลิกขวาที่ไฟล์ → Copy as path" (quotes are stripped automatically).
- [x] Buttons: ทดสอบ (runs the saved version; asks to save first if there are changes), บันทึก, ลบ (confirm dialog).
- [x] Show 422 errors next to the field; show similarity warnings after saving.

**Verify:** add a preset "เปิดโน้ต" that opens Notepad from the web → ทดสอบ opens it → say "เปิดโน้ต" → it runs without restarting Jarvis. A duplicate phrase is refused with a clear message.

## Phase 11: Web: log + settings

- [x] `/log`: date picker (only days that have logs, default today), table: เวลา · ได้ยินว่า · preset · คะแนน · ผล. Filter by result. Rows with `no_match` (or a wrong match) have "เพิ่มเป็นวลี" → choose a preset → calls add-phrase.
- [x] `/settings`:
  - Hotkey: current key + "ตั้งปุ่มใหม่" → "กดปุ่มที่ต้องการภายใน 10 วินาที" → shows the captured key → บันทึก. Refused keys show why.
  - Master switch on at startup (on/off)
  - Silence before stop (ms), max seconds, beep on/off, match threshold
  - "ทดสอบไมค์": records 3 s and shows the peak level and the current threshold, so I can see if auto-stop will work in my room
- [x] Settings saved through the API, applied without restarting (hotkey re-registered).

**Verify:** a misheard line → "เพิ่มเป็นวลี" → say the same thing again → it matches. Change the hotkey to Right Ctrl → works immediately; Caps Lock is normal again.

## Phase 12: Daily use + polish

- [x] Startup shortcut keeps running `pythonw -m jarvis listen` (now with the web). Nothing else to start.
- [x] `README.md`: how it works now (diagram), how to build the web (`cd web && npm ci && npm run build`), "Install as app" in Chrome (open `http://127.0.0.1:3003` → ⋮ → Cast, save and share → Install page as app) so it has its own window and taskbar icon, screenshots of the 4 pages, the hotkey limitation below.
- [x] Known limitation in the README: the hotkey doesn't work while an **administrator** window is focused (e.g. Task Manager); click the web button instead.
- [x] Update the Launchers `jarvis-start.bat` comment if needed (no new launcher).
- [x] Portfolio `projects.ts`: update the Jarvis entry (web UI, toggle talk, presets editor).

**Verify:** sign out and in → `http://127.0.0.1:3003` works with no window open; the installed app opens in its own window.

---

## What I have to do myself

| When | What |
|---|---|
| Phase 7 | Tell Claude Code if Caps Lock is a bad choice for me (it's changeable later) |
| Phase 9 | Node LTS installed (already) |
| Phase 12 | Install the page as an app in Chrome; pin it to the taskbar |

## Later (not now)

- `spending` action from `PLAN-spending.md` (the editor picks it up from `/api/action-types`)
- Tray icon
- Wake word
