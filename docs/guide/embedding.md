# Embedding

Every run writes `<slug>.embed.html` (the snippet) and copies `audio-smith-player.js` next to the
audio. The player is a dependency-free web component, about 6.5 KB gzipped.

```html
<audio-smith-player src="/media/audio/letter.mp3" captions="/media/audio/letter.vtt"
                    label="Listen to Dad read this letter" size="kid">
  <audio controls src="/media/audio/letter.mp3"></audio>
</audio-smith-player>
<script type="module" src="/media/audio/audio-smith-player.js"></script>
```

## Player attributes

| Attribute | Meaning |
|---|---|
| `src` | MP3 URL (also taken from the inner `<audio>`) |
| `captions` | WebVTT URL |
| `label` | Text next to the play button |
| `size` | `default` or `kid` (a large friendly button) |
| `tracks` | JSON list of language tracks, for the language toggle |
| `peaks` | JSON list of waveform peaks from the manifest; a flat bar is used when absent |
| `theme` | Colour theme override |
| `download` | Show a download link |
| `artist` | Name shown in the media session (lock screen controls) |
| `*-label` | Translations of built-in text: `play-label`, `pause-label`, `replay-label`, `retry-label`, `error-label`, `offline-label`, `loading-label`, `paused-label`, `ended-label`, `captions-on-label`, `captions-off-label` |

The player remembers where the listener stopped (playback position only, in `localStorage`) and
shows a live waveform and captions.

## Keyboard map

| Key | Action |
|---|---|
| Space or K | Play or pause |
| Left arrow | Back 5 seconds |
| Right arrow | Forward 5 seconds |
| Home / End | Jump to start / end (when the waveform has focus) |
| C | Captions on or off |
| L | Next language (when there are two or more) |

## Works without JavaScript

The inner `<audio controls>` is the fallback. With JavaScript off, or if the script fails to load,
visitors see the browser's native audio controls and still hear the narration. The captions
`<track>` is included there too.

## Configure the snippet once

Set these in `audio-smith.toml` (or as `AUDIO_SMITH_EMBED_*` variables) so the snippet matches your site:

| Setting | Default | Meaning |
|---|---|---|
| `embed_label` | `Listen` | Player label |
| `embed_size` | `default` | `default` or `kid` |
| `embed_media_base` | empty | Prefix for media URLs, such as `/media/audio/` |
| `embed_script_path` | `/media/audio/audio-smith-player.js` | Where your site serves the player script |
| `embed_script_mode` | `self` | `self` serves the copied script; `jsdelivr` pins the CDN URL to the exact version |

## Inject markers

Injection never re-serializes your HTML. It splices text between two comments:

```html
<!-- audio-smith:start -->
...player snippet...
<!-- audio-smith:end -->
```

- If the markers exist, only the bytes between them change. Re-running is idempotent.
- If they do not, one marked block is added after the first element matching `--selector`
  (default `h1`; supports `tag`, `tag#id`, and `tag.class`).
- `mr-audio-smith inject page.html --manifest path/to/slug.manifest.json --dry-run` prints the diff
  and writes nothing.

## Marking up your page

| Markup | Effect |
|---|---|
| `data-narrate` on a root element | Only this subtree is read. Put it on `<main>` or `<article>` |
| `data-narrate="skip"` | Never read |
| `data-narrate="parent"` | Goes to the parent track only |
| `data-narrate-verbatim` | Read exactly as written |
| `data-narrate-role="signature"` | The sign-off, read verbatim as the last chunk |

Navigation, emoji names, and list numbers are never narrated.
