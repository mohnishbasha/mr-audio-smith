# mr-audio-smith for Goose

Goose speaks MCP natively, so mr-audio-smith plugs in as a command-line extension.

1. Install mr-audio-smith with the MCP extra: `uv tool install "mr-audio-smith[mcp,kokoro]"`.
2. Merge `toolkit.yaml` into `~/.config/goose/config.yaml` (or run `goose configure`, choose
   Add Extension, Command-line Extension, and enter `mr-audio-smith mcp --transport stdio`).
3. Ask Goose: "Narrate https://example.com/letter.html for a five-year-old with the voice dad."

Tools: `mr_audio_smith_narrate`, `mr_audio_smith_script`, `mr_audio_smith_render`,
`mr_audio_smith_list_voices`, `mr_audio_smith_list_profiles`, `mr_audio_smith_list_backends`,
`mr_audio_smith_status`, `mr_audio_smith_recommend`.

Cloned voices must be registered with a consent record first (`mr-audio-smith voice add`); the
tools never bypass that check. Set `AUDIO_SMITH_DEFAULT_BACKEND` and `AUDIO_SMITH_MAYA2_URL` under
`envs` to point at a Maya 2 server.
