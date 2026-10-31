# Security: Jarvis

Security rules and audit checklist for Jarvis (local Python voice launcher on Windows: tap-to-talk hotkey or web button, faster-whisper, fuzzy matching, Piper, plus a local web UI served by the same process on `127.0.0.1:3003`). Claude Code: follow these rules while writing code, and follow **Audit procedure** at the bottom when asked to "run the security audit".

## What we protect

| Asset | Where it lives | Why it matters |
|---|---|---|
| My PC | The apps and files presets can open | Jarvis can start programs on my machine |
| The local web API | `127.0.0.1:3003` | Whoever can write presets or press "test" can start any program on my PC |
| Voice recordings and transcripts | `logs/` | What I (and people near me) said |
| `presets.json` | Project folder | Decides what speech and the web can trigger |
| `settings.json` | Project folder | Hotkey, thresholds |
| `SLIPS_API_TOKEN` | Jarvis `.env` | Read access to my spending data |

## Entry points

1. **Microphone audio**: my voice, but also people nearby, videos, games and calls
2. **The local web API** (`127.0.0.1:3003`): my browser, but also **any web page open in that browser** can try to send requests to localhost (CSRF, DNS rebinding)
3. `presets.json` and `settings.json` (edited through the API or by hand)
4. Global keyboard hook (`keyboard` library) — sees every key I press
5. Downloaded model files (Whisper, Piper voices) and npm packages for the web
6. Responses from the Slip Tracker API

## Project rules

- [ ] Speech can only **select a preset by name**. Transcript text is never used to build a command, a path, a URL or an argument.
- [ ] No `shell=True`, `os.system`, `eval` or `exec` anywhere. Programs start with `subprocess.Popen([path, *args])` or `os.startfile` using values from `presets.json` only.
- [ ] Below the match threshold → do nothing (and say "ไม่เข้าใจ"). Never "best guess" a preset.
- [ ] It only listens after a key press or a click, stops by itself after silence or `max_seconds`, and never listens continuously. The master switch "off" unregisters the hotkey and disables the mic button. If a wake word is added, presets that close apps or change files require a spoken or key confirmation.
- [ ] Keyboard hook: register only the configured hotkey. Never record, log or store any other key presses. `/api/hotkey/capture` returns only the one combo pressed and doesn't save it.
- [ ] Jarvis runs as my normal user, never as administrator. Autostart uses the Startup folder, not a service or a scheduled task with highest privileges.
- [ ] `presets.json` is validated on load (known action types only, required fields present). Invalid file → refuse to start with a clear error.
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
- [ ] `run`: path must be absolute, exist and end in `.exe`; args are a list of strings (max 20, each ≤ 500 chars). Never joined into a command string. Shells and script hosts (`cmd`, `powershell`, `pwsh`, `wscript`, `cscript`, `mshta`, `rundll32`, `wsl`, ...) are refused from the web: with args they would turn "start a program" into "run any command". The check follows symlinks and ignores trailing dots/spaces; it is best effort (a renamed copy gets past it), and `presets.json` itself is yours to edit.
- [ ] `open`: path must be absolute and exist, and must not be a script (`.bat .cmd .ps1 .vbs .js .hta .msi ...`) or one of the shells above.
- [ ] `chrome`: each URL must be `http://` or `https://` only.
- [ ] `uri`: scheme must match `^[a-z][a-z0-9+.-]*:` and is refused if it is `file`, `javascript`, `vbscript`, `data`, `shell`, `search-ms`, `ms-msdt`, or starts with `ms-` (Windows protocol handlers that have been abused to run code).
- [ ] Preset names `^[a-z0-9-]{1,32}$`; phrases ≤ 100 chars, ≤ 20 per preset; reply ≤ 200 chars; ≤ 20 steps; `wait` 0–30 s.
- [ ] Saves are atomic (`.tmp` + `os.replace`) and keep `presets.json.bak`. An invalid save leaves `presets.json` untouched.
- [ ] "Test" (`POST /api/presets/{name}/test`) runs the **saved** preset only, never a body sent with the request.

### Slip Tracker integration (spending questions)
- [ ] `SLIPS_API_URL` and `SLIPS_API_TOKEN` come from Jarvis' `.env` only; never in `presets.json`, code, logs or error messages.
- [ ] `SLIPS_API_URL` must point to `127.0.0.1` / `localhost`; refuse any other host.
- [ ] Jarvis only calls the read-only `GET /summary`; it never sends writes to Slip Tracker.
- [ ] 5 s timeout; on failure Jarvis speaks a generic message ("ระบบสลิปยังไม่เปิด"), details go to the log without the token.
- [ ] Spoken amounts are not written to the transcript log (only the question and which preset ran).
- [ ] Remember: answers are spoken out loud, so anyone in the room hears my spending.

### Files that must never be tracked
`.env`, `logs/`, `voices/`, `models/`, `.venv/`, any recorded `.wav`, `settings.json`, `presets.json.bak`, `web/node_modules/`, `web/.next/`, `web/out/`.

### Tests that must exist
- [ ] Wrong `Host` → 403
- [ ] POST without `X-Jarvis` → 403; POST with a foreign `Origin` → 403
- [ ] `uri` with `file:` / `ms-msdt:` → 422; `chrome` with `javascript:` → 422; `run` with a relative path → 422
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
