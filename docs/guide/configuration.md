# Configuration

## Precedence

From highest to lowest:

1. Command line flags
2. `AUDIO_SMITH_*` environment variables (plus the provider-standard `OLLAMA_HOST`,
   `ANTHROPIC_API_KEY`, and `OPENAI_API_KEY`)
3. `audio-smith.toml`, found by walking up from the current directory (the first one wins)
4. Built-in defaults

Unknown keys in the project file are ignored with a warning, so a file written for a newer version
still loads. **Secrets are never read from the file.** Keys whose names contain `key`, `token`, or
`secret` are ignored with a warning; use environment variables instead.

## audio-smith.toml

```toml
default_profile = "kid-5"
default_voice = "dad"
default_backend = "maya2"
llm = "ollama:qwen3:14b"
out_dir = "./media/audio"
voices_dir = "~/.config/audio-smith/voices"
profiles_dir = "./profiles"
qa_threshold = 0.75
embed_label = "Listen to Dad read this letter"
embed_size = "kid"
embed_media_base = "/media/audio/"
embed_script_path = "/media/audio/audio-smith-player.js"
```

Every setting is a key of the same name as the environment variable minus the prefix, lowercased.

## Settings and environment variables

| Variable | Default | Meaning |
|---|---|---|
| `AUDIO_SMITH_ENV` | `prod` | `dev`, `stage`, or `prod` |
| `AUDIO_SMITH_LOG_LEVEL` | `info` | `debug`, `info`, `warning`, `error` |
| `AUDIO_SMITH_LOG_FORMAT` | `pretty` | `pretty` or `json` |
| `AUDIO_SMITH_CACHE_DIR` | `~/.cache/audio-smith` | Content-addressed cache |
| `AUDIO_SMITH_OUT_DIR` | `./audio` | Where narrations are written |
| `AUDIO_SMITH_VOICES_DIR` | `~/.config/audio-smith/voices` | Voice records (mode 0700) |
| `AUDIO_SMITH_PROFILES_DIR` | `./profiles` | Project profiles |
| `AUDIO_SMITH_DEFAULT_PROFILE` | `kid-5` | Profile when `--profile` is omitted |
| `AUDIO_SMITH_DEFAULT_VOICE` | unset | Voice when `--voice` is omitted |
| `AUDIO_SMITH_DEFAULT_BACKEND` | `maya2` | Backend when `--backend` is omitted |
| `AUDIO_SMITH_MAYA2_URL` | `http://127.0.0.1:8080/v1` | Maya 2 server |
| `AUDIO_SMITH_MAYA2_MODE` | `http` | `http` or `inproc` |
| `AUDIO_SMITH_OPENAI_COMPAT_URL` | `http://127.0.0.1:8000/v1` | OpenAI-compatible TTS server |
| `AUDIO_SMITH_OPENAI_TTS_MODEL` | `gpt-4o-mini-tts` | Model for the `openai` backend |
| `AUDIO_SMITH_LLM` | `ollama:qwen3:14b` | Script writer: `ollama:<model>`, `anthropic:<model-id>`, `openai_compat:<base_url>#<model>`, `fake` |
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | Ollama server (also `AUDIO_SMITH_OLLAMA_HOST`) |
| `ANTHROPIC_API_KEY` | unset | For the `anthropic` provider (needs the `cloud` extra) |
| `OPENAI_API_KEY` | unset | For the `openai` backend |
| `AUDIO_SMITH_QA_THRESHOLD` | `0.75` | Minimum speaker similarity; overrides the profile |
| `AUDIO_SMITH_TAKES_PER_CHUNK` | `2` | Takes per chunk (1 to 10) |
| `AUDIO_SMITH_SYNTH_CONCURRENCY` | `2` | Parallel synthesis requests (1 to 16) |
| `AUDIO_SMITH_STUDIO_PORT` | `7341` | Studio port (always on 127.0.0.1) |
| `AUDIO_SMITH_SERVER_HOST` | `127.0.0.1` | Reserved for `serve` |
| `AUDIO_SMITH_SERVER_PORT` | `7340` | Reserved for `serve` |
| `AUDIO_SMITH_SERVER_TOKEN` | unset | Reserved for `serve`; required to bind beyond localhost |
| `AUDIO_SMITH_MAX_FETCH_BYTES` | `5242880` | Page size limit (5 MiB) |
| `AUDIO_SMITH_FETCH_TIMEOUT_S` | `20` | Fetch time limit in seconds |
| `AUDIO_SMITH_ALLOW_PRIVATE` | `false` | Allow fetching private or loopback addresses |
| `AUDIO_SMITH_ACCEPT_NONCOMMERCIAL` | `false` | Allow backends with non-commercial weights |
| `AUDIO_SMITH_EMBED_LABEL` | `Listen` | Player label |
| `AUDIO_SMITH_EMBED_SIZE` | `default` | `default` or `kid` |
| `AUDIO_SMITH_EMBED_MEDIA_BASE` | empty | Prefix for media URLs in the snippet |
| `AUDIO_SMITH_EMBED_SCRIPT_MODE` | `self` | `self` or `jsdelivr` |
| `AUDIO_SMITH_EMBED_SCRIPT_PATH` | `/media/audio/audio-smith-player.js` | Player script URL |

## Safety defaults

- Fetching refuses private networks, loopback, and cloud metadata addresses unless you pass
  `--allow-private`. Only `http`, `https`, and local `.html` or `.md` files are accepted.
- The tool sends no telemetry. Cloud providers are used only when you configure them, and `doctor`
  warns when one is active.
