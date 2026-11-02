# Use from your agent

mr-audio-smith exposes one MCP server (`mr-audio-smith mcp`) that Claude Code, Goose, and OpenCode
speak natively, plus a Pi extension that talks to the REST server. Install the extra first:

    uv tool install "mr-audio-smith[mcp,kokoro]"

| Harness | Setup | Files |
|---|---|---|
| Claude Code | `claude mcp add mr-audio-smith -- mr-audio-smith mcp --transport stdio`, then copy the skill | `integrations/claude-code/` |
| Goose | merge `toolkit.yaml` into `~/.config/goose/config.yaml` (or `goose configure`, Command-line Extension) | `integrations/goose/` |
| OpenCode | copy the `mcp` block from `opencode.json.example` into `opencode.json` | `integrations/opencode/` |
| Pi | install `@mr-audio-smith/pi-extension`, set `AUDIO_SMITH_SERVER_URL` and `AUDIO_SMITH_SERVER_TOKEN` | `integrations/pi/` |

## Tools

| Tool | Input | Output |
|---|---|---|
| `mr_audio_smith_narrate` | source, profile, voice, backend, langs, inject_path | manifest path, tracks (lang, file, duration), warnings; streams progress |
| `mr_audio_smith_script` | source, profile | script path, chunk count, estimated minutes |
| `mr_audio_smith_render` | script_path, chunks, voice, backend | files |
| `mr_audio_smith_list_voices` | none | id, display name, backends, cloned |
| `mr_audio_smith_list_profiles` | none | id, version, description |
| `mr_audio_smith_list_backends` | none | id, available, languages, cloning, license |
| `mr_audio_smith_status` | none | the `doctor` report |
| `mr_audio_smith_recommend` | source or description | profile, backend, reason |

Every tool enforces voice consent: a cloned voice must be registered with
`mr-audio-smith voice add` (your own voice or one you have written permission to use).

## Remote GPU box

Run `AUDIO_SMITH_SERVER_TOKEN=... mr-audio-smith serve --host 0.0.0.0` on the machine with the GPU
and Maya 2. Pi talks to it directly; other agents can call the CLI with
`mr-audio-smith run <url> --server https://gpu-box:7340 --token ...`, or run `mr-audio-smith mcp`
on the GPU box with `--transport http`.

## Verifying a setup

`tests/integration/test_harness_configs.py` launches the exact command each config declares and
checks the MCP handshake lists all eight tools; CI runs it on staging and release.
