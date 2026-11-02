# Studio

Studio is a local review tool for narration. Use it when a page matters enough to listen to every
sentence before you publish.

```bash
mr-audio-smith studio              # opens http://127.0.0.1:7341/?token=...
mr-audio-smith studio --port 7500 --out ./media/audio --no-open
```

## What it does

- Lists the narrations in your output directory and shows each script chunk beside its text.
- **Edit** a chunk with live validation against the Script Markdown rules (pause markers, length).
- **Render takes** for a chunk, **compare two takes** side by side, and keep the better one.
  Take 0 is the original narration.
- **Re-master** the track and preview it in the real `<audio-smith-player>`.
- **Approve** the script (recorded as `approved: true` in the manifest).
- **Inject** the player into a page, with a diff preview before anything is written.

Studio edits the same files the CLI writes, so you can mix both freely.

## Security model

Studio is built to be safe to leave open on a laptop:

- **Localhost only.** It always binds to 127.0.0.1, never to a network address. The port comes from
  `--port` or `AUDIO_SMITH_STUDIO_PORT` (default 7341).
- **Per-session token.** A random token is generated each time Studio starts and is part of the URL
  it prints. Every `/api` and `/media` request needs it in the `X-Studio-Token` header; without it
  the answer is 403. The page keeps the token in memory only.
- **Strict Content-Security-Policy.** `default-src 'self'; media-src 'self' blob:; connect-src 'self'
  blob:; img-src 'self' data:; style-src 'self'; script-src 'self'; frame-ancestors 'none'`. No
  inline scripts and no external requests. Audio is fetched with the token and handed to the player as
  `blob:` URLs.
- **Other headers.** `X-Content-Type-Options: nosniff` and `Referrer-Policy: no-referrer`.
- **Bounded writes.** Injection is limited to files inside the project root, and paths are validated.
- **No telemetry.** Studio makes no analytics calls.

If you see a 403, open the exact URL Studio printed, including the token.
