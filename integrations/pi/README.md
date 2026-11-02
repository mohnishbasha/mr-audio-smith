# @mr-audio-smith/pi-extension

A [Pi](https://github.com/earendil-works/pi) extension that narrates pages through a running
mr-audio-smith server (REST, `/v1`). It registers five tools, three slash commands, and a
session-start context hook that tells the agent which voices and profiles exist.

Built against `@earendil-works/pi-coding-agent` 1.4.0 (`ExtensionAPI`, TypeBox tool schemas,
the `onUpdate` progress callback, and the `session_start` event). The package is a dev
dependency only; the bundle imports its types and nothing else at run time.

## Install

```bash
cd integrations/pi
npm install
npm run build          # bun build to dist/index.js (ESM)
pi install ./integrations/pi   # or: pi -e ./integrations/pi/dist/index.js
```

Start the server first: `mr-audio-smith serve` (see the server docs for tokens).

## Configuration

| Variable                   | Default                 | Purpose                                          |
| -------------------------- | ----------------------- | ------------------------------------------------ |
| `AUDIO_SMITH_SERVER_URL`   | `http://127.0.0.1:8765` | Base URL of the server                           |
| `AUDIO_SMITH_SERVER_TOKEN` | unset                   | Bearer token sent as `Authorization: Bearer ...` |

Programmatic use: `createExtension({ config: { baseUrl, token } })` from `src/index.ts`.
Server errors arrive as problem+json and are shown as `code: detail (hint: ...)`.

## Tools

| Tool                           | Input                                          | Result                                                                                       |
| ------------------------------ | ---------------------------------------------- | -------------------------------------------------------------------------------------------- |
| `mr_audio_smith_narrate`       | `{source, profile?, voice?, backend?, langs?}` | Streams `stage: N%, chunk n of m`, then lists tracks (language, file, duration) and warnings |
| `mr_audio_smith_list_voices`   | `{}`                                           | Registered voices, cloned ones marked                                                        |
| `mr_audio_smith_list_profiles` | `{}`                                           | Profiles with version and description                                                        |
| `mr_audio_smith_list_backends` | `{}`                                           | Backends with availability, languages, cloning, license                                      |
| `mr_audio_smith_status`        | `{job_id?}`                                    | Job status, or server health and readiness when no id is given                               |

Cloning needs a voice registered on the server with a consent record. Unregistered or
consent-less voices are refused by the server; the extension cannot register voices.

## Slash commands

- `/narrate <url> [profile] [voice]` runs a job and reports progress as notifications.
- `/voices` lists voices and profiles.
- `/audio-status [job_id]` shows server readiness, or one job.

## Development

```bash
npm run typecheck && npm run lint && npm test && npm run coverage
```

Coverage threshold: 70 percent of lines under `src`.

## Manual test in Pi

Record the result in `docs/TEST_PLAN.md` section 5.25.

- [ ] Server running with the mock backend and a token; env vars exported in the Pi shell
- [ ] Pi starts with the extension loaded and no error banner
- [ ] `/voices` lists the registered voices and profiles
- [ ] `/audio-status` reports healthy and ready
- [ ] `/narrate <fixture page url>` shows stage and chunk progress, then the track list
- [ ] Asking the agent "narrate this page for my kid" calls `mr_audio_smith_narrate`
- [ ] The agent already knows the voice and profile names at session start (context hook)
- [ ] Stop the server, restart Pi: it starts normally and tools report an unreachable server
- [ ] A voice without consent is refused with a readable message
