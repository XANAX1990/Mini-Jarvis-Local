# Jarvis web

The browser UI for Jarvis: Next.js (App Router, TypeScript, Tailwind) built as a **static export**. The Jarvis Python process serves the result from `web/out/` on `http://127.0.0.1:3003`, so nothing from Node runs at runtime.

```
cd web
npm ci
npm run build      # writes web/out/ ; then restart Jarvis (python -m jarvis listen)
```

Development with hot reload (needs `JARVIS_DEV=1` on the Python side, which lets `http://localhost:3004` call the API):

```
set JARVIS_DEV=1 && python -m jarvis listen     # in the repo root
npm run dev                                      # in web/, http://localhost:3004
```

Rules (see `../SECURITY.md`): every request goes through `src/lib/api.ts`, which sends `Content-Type: application/json` and `X-Jarvis: 1`; text from the API (transcripts, preset names, paths) is rendered as plain text, never as HTML.
