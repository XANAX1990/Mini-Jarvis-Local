# Security: Jarvis

Security rules and audit checklist for Jarvis (local Python voice launcher on Windows: tap-to-talk hotkey or web button, faster-whisper, fuzzy matching, Piper, plus a local web UI served by the same process on `127.0.0.1:3003`). Claude Code: follow these rules while writing code, and follow **Audit procedure** at the bottom when asked to "run the security audit".

## What we protect

| Asset | Where it lives | Why it matters |
|---|---|---|
| My PC | The apps and files presets can open | Jarvis can start programs on my machine |
| The local web API | `127.0.0.1:3003` | Whoever can write presets or press "test" can start any program on my PC |
| Voice recordings and transcripts | `logs/` | What I (and people near me) said |
| `presets.json` | Project folder | Decides what speech and the web can trigger |
| `programs.json` | Project folder | The allow-list of programs a preset can start: whoever can add to it without my click can start any program |
| `settings.json` | Project folder | Hotkey, thresholds |
| `SLIPS_API_TOKEN` | Jarvis `.env` | Read access to my spending data |

## Entry points

1. **Microphone audio**: my voice, but also people nearby, videos, games and calls
2. **The local web API** (`127.0.0.1:3003`): my browser, but also **any web page open in that browser** can try to send requests to localhost (CSRF, DNS rebinding)
3. `presets.json`, `programs.json` and `settings.json` (edited through the API or by hand)
4. Global keyboard hook (`keyboard` library) — sees every key I press
5. Downloaded model files (Whisper, Piper voices) and npm packages for the web
6. Responses from the Slip Tracker API

## Project rules

- [ ] Speech can only **select a preset by name**. Transcript text is never used to build a command, a path, a URL or an argument.
- [ ] No `shell=True`, `os.system`, `eval` or `exec` anywhere. A `run` step starts a program with `subprocess.Popen([path, *args])` using the path and args of its entry in `programs.json` (a preset only names the entry); `open` and `uri` use `os.startfile` with values from `presets.json` only.
- [ ] Below the match threshold → do nothing (and say "ไม่เข้าใจ"). Never "best guess" a preset.
- [ ] It only listens after a key press or a click, stops by itself after silence or `max_seconds`, and never listens continuously. The master switch "off" unregisters the hotkey and disables the mic button. If a wake word is added, presets that close apps or change files require a spoken or key confirmation.
- [ ] Keyboard hook: register only the configured hotkey. Never record, log or store any other key presses. `/api/hotkey/capture` returns only the one combo pressed and doesn't save it.
- [ ] Jarvis runs as my normal user, never as administrator, and refuses to start when it is elevated (`jarvis/privileges.py`, every command). Autostart uses the Startup folder, not a service or a scheduled task with highest privileges.
- [ ] `presets.json` and `programs.json` are validated on load (known action types only, required fields present, every `run` step names a program that exists). Invalid file → refuse to start with a clear error.
- [ ] Audio is not kept by default: `last.wav` is overwritten each time. Transcript logs are kept for a limited time (e.g. 30 days) and never committed.
- [ ] Models are downloaded only from known repos, versions noted in the README; voice and wake-word licenses noted (non-commercial ones are for personal use only).

### Local web API (`127.0.0.1:3003`)
- [ ] uvicorn binds to `127.0.0.1` only, never `0.0.0.0`. No ngrok, no port forwarding, never deployed.
- [ ] **Host allow-list:** every request whose `Host` header isn't `127.0.0.1:3003` or `localhost:3003` → 403 (blocks DNS rebinding).
- [ ] **Every request except GET and HEAD** (POST/PUT/DELETE/OPTIONS...) must have (HEAD is only the browser's link prefetch of static pages; API routes don't answer it, and the Host check still applies):
  - header `X-Jarvis: 1` (a page on another site can't add a custom header without a CORS preflight, which we never approve)
  - `Origin` equal to `http://127.0.0.1:3003` or `http://localhost:3003` (plus `http://localhost:3004` only when `JARVIS_DEV=1`); missing or other → 403
  - `Content-Type: application/json`
- [ ] **No CORS** in normal mode. In dev mode (`JARVIS_DEV=1`) allow only the exact origin `http://localhost:3004`, never `*`, never with credentials.
- [ ] GET endpoints never change anything (no "GET to run a preset").
- [ ] Every request body is validated with pydantic (types, lengths, enums). Unknown fields are rejected.
- [ ] Errors returned to the browser: short message + field name. No stack traces, file paths or exception text.
- [ ] The web UI shows transcripts, preset names and paths as plain text (React escaping). No `dangerouslySetInnerHTML`.

### Presets written from the web
- [ ] Action types come from a fixed list (`run`, `open`, `uri`, `chrome`, `wait`, later `spending`). Unknown type → 422.
- [ ] `run`: see **Programs** below: a preset only names a program, it never carries a path or args.
- [ ] `open`: from the web only a folder, or a file whose type is one of `pdf txt md docx xlsx pptx png jpg jpeg gif mp3 mp4`, judged after symlinks and short names are resolved and trailing dots/spaces dropped. No `.lnk`, `.url`, scripts or programs. A hand-edited `presets.json` is not checked.
- [ ] `chrome`: each URL must be `http://` or `https://` only.
- [ ] `uri`: scheme must match `^[a-z][a-z0-9+.-]+:` (two characters or more: a single letter is a drive path such as `C:\...`, which would start any file) and is refused if it is `file`, `javascript`, `vbscript`, `data`, `shell`, `search-ms`, `ms-msdt`, or starts with `ms-` (Windows protocol handlers that have been abused to run code).
- [ ] Preset names `^[a-z0-9-]{1,32}$`; phrases ≤ 100 chars, ≤ 20 per preset; reply ≤ 200 chars; ≤ 20 steps; `wait` 0–30 s.
- [ ] Saves are atomic (`.tmp` + `os.replace`) and keep `presets.json.bak`. An invalid save leaves `presets.json` untouched.
- [ ] "Test" (`POST /api/presets/{name}/test`) runs the **saved** preset only, never a body sent with the request.

### Programs (`programs.json`): the allow-list for `run`
- [ ] A preset's `run` step is `{"type": "run", "program": "<name>"}` and nothing else. A `path` or `args` in a preset is refused (422), and so is a name that is not in `programs.json`.
- [ ] An entry is `{path, args}`: path absolute, ending in `.exe`, and the file must exist when it is added; args are a list of strings (max 20, each ≤ 500 chars), never joined into a command string. Names `^[a-z0-9-]{1,32}$`.
- [ ] **Adding a program from the web (`POST /api/programs`) needs a Yes/No box on the desktop** (`MessageBoxW`, topmost, default button No) that shows the name, the real path (variables and links resolved) and every argument. No, closed, or no answer within 60 s → nothing is saved (403). Only one box at a time: a second request gets 409. A request that fails validation never opens a box.
- [ ] Deleting a program needs no box (it only shrinks the list) but is refused (409) while a preset uses it.
- [ ] Editing `programs.json` by hand needs nothing: whoever can edit the file can already run anything as me.
- [ ] Saves are atomic and keep `programs.json.bak`. `run` steps that still carry their own path are moved into `programs.json` automatically at start (once; `presets.json.bak` keeps the old file).

### Slip Tracker integration (spending questions)
- [ ] `SLIPS_API_URL` and `SLIPS_API_TOKEN` come from Jarvis' `.env` only; never in `presets.json`, code, logs or error messages.
- [ ] `SLIPS_API_URL` must point to `127.0.0.1` / `localhost`; refuse any other host. Redirects are never followed (urllib would forward `X-Local-Token` to the new host).
- [ ] Jarvis only calls the read-only `GET /summary`; it never sends writes to Slip Tracker.
- [ ] 5 s timeout; on failure Jarvis speaks a generic message ("ระบบสลิปยังไม่เปิด"), details go to the log without the token.
- [ ] Spoken amounts are not written to the transcript log (only the question and which preset ran).
- [ ] Remember: answers are spoken out loud, so anyone in the room hears my spending.

### Files that must never be tracked
`.env`, `logs/`, `voices/`, `models/`, `.venv/`, any recorded `.wav`, `settings.json`, `presets.json` and `programs.json` (my own presets and programs; `presets.example.json` and `programs.example.json` are the tracked starters that are copied on first run), their `.bak` and `.tmp` files, `web/node_modules/`, `web/.next/`, `web/out/`.

### Accepted risks (decided by the owner, 2026-11-01)
- **CSP allows `script-src 'unsafe-inline'`.** The Next.js static export puts its start-up scripts inline in every page. The page loads nothing from other origins (`default-src 'self'`, `connect-src 'self'`, no external fonts or scripts). Revisit with script hashes if the page ever shows content from outside.
- **The local API has no login.** Host, Origin and `X-Jarvis` protect against web pages and DNS rebinding, not against another program running as me, which could do the same things without the API.

- **The desktop confirmation is a control on the desktop, not on the program.** It stops web pages and anything that can only call the API; it does not stop software that already runs as me and can click on my desktop (UI automation). I accept that, as with the missing login.

### Known gaps (not decided yet)
- **`uri` steps accept any scheme that is not blocked.** Another app's protocol handler (`steam:`, `discord:`, ...) can be started from the web. An allow-list like the one for `run` would close it.

### Tests that must exist
- [ ] Wrong `Host` → 403
- [ ] POST without `X-Jarvis` → 403; POST with a foreign `Origin` → 403
- [ ] `uri` with `file:` / `ms-msdt:` → 422; `chrome` with `javascript:` → 422
- [ ] A `run` step naming a program that is not in `programs.json` → 422; a `path` or `args` in a `run` step → 422
- [ ] Adding a program: No → nothing saved; no answer in time → nothing saved; a request that fails validation never opens a box; a second request while a box is open → 409; the box shows the real path and every argument
- [ ] Deleting a program a preset uses → 409
- [ ] `open` with `.bat` / `.lnk` / `.url` / `.exe` → 422
- [ ] The test run never changes the owner's `presets.json`, `programs.json` or `settings.json`
- [ ] Invalid preset save leaves `presets.json` byte-for-byte unchanged

## Rules that apply to every project

### Secrets
- [ ] No secret in source code, tests, fixtures, docs, screenshots or commit messages. Secrets come from `.env` / the host's env settings (Vercel, Firebase) / n8n credentials.
- [ ] `.env*` files (except `.env.example`) are in `.gitignore`; `.env.example` lists names only, no values.
- [ ] Different secrets for dev and prod.
- [ ] If a secret was ever committed: **rotate it first**, then clean history. Deleting the file is not enough.

### Private data
- [ ] Logs never contain secrets, tokens, full emails or other personal data.
- [ ] Error messages sent to a browser or chat don't include stack traces, file paths, internal URLs or DB details.
- [ ] Images committed to the repo (README screenshots, assets) are checked for personal data and have EXIF stripped.

### Dependencies
- [ ] Versions locked (`package-lock.json` / pinned `requirements.txt`).
- [ ] `npm audit --omit=dev` / `pip-audit` show no high or critical issues, or each one is noted with why it doesn't apply.
- [ ] No packages added "just in case"; unused packages removed.

### Least privilege
- [ ] Every key, token and DB user has only the access this project needs (one database, read/write only where needed, narrowest OAuth scopes).

---

## Audit procedure (for Claude Code)

Run this when I say "run the security audit", before making a repo public, and before a big deploy.

1. List every tracked file with `git ls-files` and check **each one** against the rules in this file. Also check untracked files that aren't ignored: `git status --porcelain`.
2. Search for secrets in the current tree **and in history**:
   ```bash
   git grep -nIiE "(secret|token|password|passwd|api[_-]?key|bearer|mongodb(\+srv)?://)"
   git grep -nIE "[A-Za-z0-9+/_-]{60,}={0,2}"     # long tokens
   git grep -nIE "\b[0-9a-f]{32}\b"               # 32-hex secrets
   git log -p --all | grep -nIiE "(secret|token|password|bearer|mongodb(\+srv)?://)"
   ```
3. Check `.gitignore` against the private files listed for this project; confirm none of them is tracked.
4. Read every place that handles untrusted input (listed under **Entry points**) and check it against the project rules.
5. Run the dependency audit (`npm audit --omit=dev` and/or `pip-audit`).
6. **Report first, don't fix yet.** Output one table:

   | File | Line | Rule broken | Severity (High / Medium / Low) | Suggested fix |
   |---|---|---|---|---|

   Then a short list of rules that passed. Wait for my "ok" before changing anything. Fix High items first, one commit per fix.
7. If a real secret is found in the tree or history, **stop** and tell me which one, so I can rotate it before anything else.
