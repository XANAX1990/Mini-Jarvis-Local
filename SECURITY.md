# Security: Jarvis

Security rules and audit checklist for Jarvis (local Python voice launcher on Windows: push-to-talk, faster-whisper, fuzzy matching, Piper). Claude Code: follow these rules while writing code, and follow **Audit procedure** at the bottom when asked to "run the security audit".

## What we protect

| Asset | Where it lives | Why it matters |
|---|---|---|
| My PC | The apps and files presets can open | Jarvis can start programs on my machine |
| Voice recordings and transcripts | `logs/` | What I (and people near me) said |
| `presets.json` | Project folder | Decides what speech can trigger |

## Entry points

1. **Microphone audio**: my voice, but also people nearby, videos, games and calls
2. `presets.json`
3. Downloaded model files (Whisper, Piper voices)
4. The Slip Tracker API's answer (`spending` presets: read only, JSON from `127.0.0.1`)

## Project rules

- [ ] Speech can only **select a preset by name**. Transcript text is never used to build a command, a path, a URL or an argument.
- [ ] No `shell=True`, `os.system`, `eval` or `exec` anywhere. Programs start with `subprocess.Popen([path, *args])` or `os.startfile` using values from `presets.json` only.
- [ ] Below the match threshold → do nothing (and say "ไม่เข้าใจ"). Never "best guess" a preset.
- [ ] Push-to-talk stays the default, so it isn't listening all the time. If a wake word is added, presets that close apps or change files require a spoken or key confirmation.
- [ ] Jarvis runs as my normal user, never as administrator. Autostart uses the Startup folder, not a service or a scheduled task with highest privileges.
- [ ] `presets.json` is validated on load (known action types only, required fields present). Invalid file → refuse to start with a clear error.
- [ ] Audio is not kept by default: `last.wav` is overwritten each time. Transcript logs are kept for a limited time (e.g. 30 days) and never committed.
- [ ] `spending` presets only read from the local Slip Tracker API. `SLIPS_API_URL` must be `127.0.0.1` or `localhost` (the token is never sent elsewhere); the token lives in `.env` (git-ignored), never in `presets.json`, the log or the spoken answer; errors are spoken in one short line, details only in the log.
- [ ] Models are downloaded only from known repos, versions noted in the README; voice and wake-word licenses noted (non-commercial ones are for personal use only).

### Files that must never be tracked
`logs/`, `voices/`, `models/`, `.venv/`, `.env`, any recorded `.wav`.

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
