# Jarvis × Slip Tracker: Plan (add-on to mini-jarvis)

Ask Jarvis "เดือนนี้จ่ายไปเท่าไร" and hear the answer, read from the Slip Tracker API on my PC.
Put this file in the `mini-jarvis` repo as `PLAN-spending.md`.

## Working agreement (for Claude Code)

- One phase at a time; stop, tell me what to run to verify, wait for "ok". Commit after each phase.
- Keep Jarvis' rules: speech only selects a preset; no shell; scope fixed (no LLM, no free-form questions).
- The Slip Tracker API is local (`127.0.0.1:8000`) and needs `X-Local-Token`; Jarvis reads it from its own `.env` (`SLIPS_API_URL`, `SLIPS_API_TOKEN`), never from `presets.json`.
- Read only: Jarvis never changes data in Slip Tracker.

## Depends on

Slip Tracker exposes `GET /summary?from=YYYY-MM-DD&to=YYYY-MM-DD` → `{ total, count, by_category }`. If it only has `?month=`, add the `from`/`to` version there first (small change, with a test).

---

## Phase 1: Summary action

- [ ] New action type in `presets.json`: `{ "type": "spending", "period": "today" | "week" | "month" }`
- [ ] `spending.py`: work out the date range in Asia/Bangkok (week = Monday–today), call the API with a 5 s timeout, build the sentence
- [ ] **Numbers in Thai words** before TTS (the Thai voice doesn't read digits well): `pythainlp.util.bahttext` for money, Thai words for counts, e.g. "เดือนนี้จ่ายไป สี่พันสามร้อยห้าสิบบาทถ้วน จาก สามสิบสอง รายการ"
- [ ] Zero spending → "เดือนนี้ยังไม่มีรายจ่าย"; API not running → "ระบบสลิปยังไม่เปิด"; wrong token → "เชื่อมระบบสลิปไม่ได้" (details only in the log)
- [ ] Tests with a mocked API: each period, zero, API down, 401

**Verify:** `python -m jarvis run spending-month` speaks the right total (matches the Slip Tracker web page).

## Phase 2: Phrases + end to end

- [ ] Presets:
  - `spending-today`: "วันนี้จ่ายไปเท่าไร", "วันนี้ใช้ไปเท่าไร"
  - `spending-week`: "อาทิตย์นี้จ่ายไปเท่าไร"
  - `spending-month`: "เดือนนี้จ่ายไปเท่าไร", "เดือนนี้ใช้ไปเท่าไร"
- [ ] Add these phrases to Whisper's `initial_prompt`
- [ ] Check the matcher doesn't confuse the three (add a test with similar phrases)

**Verify:** say each phrase 3 times → right period every time; "เปิดโหมดเกม" still works.

## Phase 3: Polish

- [ ] README of both projects: one line about the integration + a short demo clip
- [ ] Add it to the Jarvis entry in the portfolio's `projects.ts` as a highlight

## What I have to do myself

| When | What |
|---|---|
| Phase 1 | Copy `SLIPS_API_TOKEN` from Slip Tracker's `.env` into Jarvis' `.env` |
| Phase 2 | Start Slip Tracker (`start-slips.bat`) before testing |
