# mr-audio-smith for OpenCode

OpenCode speaks MCP natively; no code is needed.

1. Install: `uv tool install "mr-audio-smith[mcp,kokoro]"`.
2. Copy the `mcp` block from `opencode.json.example` into your project's `opencode.json` (or the
   global config). Change `AUDIO_SMITH_DEFAULT_BACKEND` to `kokoro` on a machine without a GPU.
3. Ask OpenCode to narrate a page; it calls `mr_audio_smith_narrate` and reports the file paths.

Cloned voices require a consent record (`mr-audio-smith voice add`), enforced by the tool itself.
