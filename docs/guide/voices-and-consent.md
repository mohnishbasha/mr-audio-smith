# Voices and consent

mr-audio-smith can read a page in a cloned voice. That power comes with one rule: **only clone your
own voice, or a voice whose owner has given you written permission.** The tool enforces this with a
consent record that is required for every cloned voice, below every front door (CLI, Python API,
Studio). It cannot be bypassed with a flag.

## Recording a good clip

- Record 5 to 10 seconds of natural speech. The accepted range is 3 to 30 seconds, and 3 to 10
  works best.
- Use a quiet room with soft surfaces (a closet full of clothes works well). Turn off fans.
- Hold the microphone about a hand span from your mouth, and speak at your normal storytelling pace.
- Read a sentence with some expression, not a flat list of words.
- Save a mono or stereo WAV at 24 kHz or higher. 16 kHz is the minimum.
- Write down exactly what you said. The transcript improves Maya 2 cloning (`--text`).

## Registering a voice

```bash
mr-audio-smith voice add dad \
  --clip my-voice.wav \
  --name "Your Full Name" \
  --relationship self \
  --text "My dear Aadi, some days feel like a big swirly storm."
```

| Flag | Meaning |
|---|---|
| `voice_id` (argument) | Short id such as `dad`: lowercase letters, digits, and hyphens, up to 40 characters |
| `--clip` | Reference WAV (required) |
| `--name` | Speaker's full name for the consent record (required) |
| `--relationship` | `self` or `written_permission` (required) |
| `--statement` | Consent statement. For `self` you are prompted with a default statement (accepted by `--yes`); `written_permission` requires `--statement` quoting the permission |
| `--text` or `--reference-text` | Transcript of the clip |
| `--display-name` | Friendly label |
| `--date` | Consent date, `YYYY-MM-DD` (defaults to today) |
| `--replace` | Overwrite an existing voice with the same id |
| `--yes`, `-y` | Do not prompt for confirmation |

With `--relationship written_permission`, keep the written permission yourself. The record stores
the speaker's name, the relationship, the statement, and the date.

## The consent record

Each voice lives in `~/.config/audio-smith/voices/<id>/` (directory mode 0700, files 0600):

| File | Contents |
|---|---|
| `voice.yaml` | The voice record: id, display name, backend hints, reference text, consent, clip checks, clip hash |
| `reference.wav` | The clip you provided |
| `reference.24k.wav` | A 24 kHz mono copy used for synthesis and quality checks |

The consent block has these fields: `speaker_name`, `relationship` (`self` or `written_permission`),
`statement`, and `date`. The record also stores the SHA-256 hash of the clip, so editing the clip
after registration is detected. Manifests record only the voice id, never the clip or the statement.

## Clip checks and thresholds

Bad clips make bad clones, so `voice add` rejects a clip and lists every problem at once:

| Check | Threshold |
|---|---|
| Duration | 3 s minimum, 30 s maximum |
| Sample rate | At least 16 kHz |
| Clipping | Under 0.1 percent of samples at full scale |
| Signal to noise | At least 25 dB (estimated) |

Run `mr-audio-smith voice check dad` any time to re-check the clip, the consent record, the hash,
and file permissions. `--fix` tightens broad permissions.

```bash
mr-audio-smith voice list
mr-audio-smith voice check dad --fix
mr-audio-smith voice remove dad
```

## Speaker similarity

With the `qa` extra installed, each cloned chunk is compared against your reference voice. The
default threshold is 0.75 (`AUDIO_SMITH_QA_THRESHOLD` or `qa.threshold` in a profile). Chunks below
it are re-rendered with a new seed and the best take is kept. If the extra is missing, the check is
skipped and the manifest says so.

## Ethics

- Clone your own voice, or one you hold written permission for. A parent reading to a child, a
  teacher with permission from a colleague, or a narrator who signed a release are fine.
- Never clone a voice to deceive, to impersonate, or to speak words the owner would not accept.
- Clips stay on your machine, or on the TTS server you configure. They are never uploaded to a
  third party by mr-audio-smith, and they are never committed to a site repository.
- Cloud TTS backends (`openai`) do not clone; they use their own stock voices.
- Remove voices you no longer need with `voice remove`.

If a command exits with code 8, the voice has no valid consent record. See
[Troubleshooting](troubleshooting.md).
