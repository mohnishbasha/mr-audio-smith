# mr-audio-smith: Design Specification

Version: 1.0 (draft for v1). Date: 2026-11-01.

mr-audio-smith has two visual surfaces:

1. The **embed player** (`<audio-smith-player>`), seen by listeners including five-year-olds, on someone else's page.
2. The **Studio** review UI, seen by authors on localhost.

Both share one token set (prefix `--as-`). Requirements trace to PRD FR-015, FR-017, FR-022 and NFR-007, NFR-011.

---

## 1. Principles

Warm, calm, and legible. The player sits on someone else's page, often a family page read by a child, so it must feel friendly and never compete with the content.

- Quiet by default: no autoplay, no sound until a person presses play.
- Native feel: the player inherits the host font and uses one accent color.
- Readable by a five-year-old: one obvious button, a big friendly label.
- Honest states: every state (loading, error, offline) is stated in words.
- No decoration for its own sake: one signature element (the breathing waveform), nothing else animated.
- Studio is a workbench: dense but clear, mono for script text, status always pair text with color.

---

## 2. Color tokens

```css
:root {
  /* Surfaces */
  --as-bg:            #FFFFFF;
  --as-surface:       #F6F8F5;   /* player card */
  --as-surface-2:     #ECF1EA;   /* hover, track */
  --as-border:        #D7E0D3;

  /* Text */
  --as-text:          #1E2A22;
  --as-text-muted:    #5B6B60;
  --as-text-inverse:  #FFFFFF;

  /* Accent (sage, pairs with the reference site's #7daa8b theme color) */
  --as-accent:        #4E8A62;   /* play button, progress; 4.6:1 on white */
  --as-accent-hover:  #3F7552;
  --as-accent-soft:   #DCEBDF;

  /* Kid accents (kid variant only) */
  --as-sun:           #F4B740;
  --as-sky:           #5AA9E6;

  /* Feedback */
  --as-error:         #B3261E;
  --as-focus:         #1F6FEB;
}

/* Automatic dark: follows the OS unless the host forces light */
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --as-bg:            #101512;
    --as-surface:       #18201B;
    --as-surface-2:     #222C25;
    --as-border:        #2E3A32;
    --as-text:          #E8EFE9;
    --as-text-muted:    #A3B2A7;
    --as-accent:        #7DBF92;
    --as-accent-hover:  #93CEA6;
    --as-accent-soft:   #23362A;
  }
}

/* Forced dark: same values as the block above, written out in full */
:root[data-theme="dark"] {
  --as-bg:            #101512;
  --as-surface:       #18201B;
  --as-surface-2:     #222C25;
  --as-border:        #2E3A32;
  --as-text:          #E8EFE9;
  --as-text-muted:    #A3B2A7;
  --as-accent:        #7DBF92;
  --as-accent-hover:  #93CEA6;
  --as-accent-soft:   #23362A;
}
```

Notes:

- Tokens not redefined in the dark block (`--as-text-inverse`, `--as-sun`, `--as-sky`, `--as-error`, `--as-focus`) keep their light values. Where the play glyph sits on the dark-mode accent (`#7DBF92`), the glyph uses `--as-bg` for contrast instead of `--as-text-inverse`.
- In the player the tokens are scoped to the component host (`:host`) and can be overridden from the page with the same custom property names.
- Contrast targets: text on surface at least 4.5:1, accent against its background at least 3:1 for non-text UI, `--as-accent` on white is 4.6:1.

### 2.1 Studio extra tokens

Studio uses the same tokens plus:

```css
:root {
  --as-stale: #C77D12;   /* chunk needs re-render */
  --as-ok:    #2E7D4F;   /* chunk rendered and approved */
}
```

Dark values for Studio extras: `--as-stale: #E0A04A`, `--as-ok: #6FC08D`, applied under both dark selectors above.

Status pills in Studio always pair the color with a text label: Draft, Stale, Rendering, Rendered, Approved, Failed. Color is never the only signal.

---

## 3. Typography

- Player inherits the host page font by default (`font: inherit`) so it feels native. Fallback stack: `ui-rounded, "SF Pro Rounded", "Nunito", system-ui, sans-serif`.
- Studio: `Inter` for UI, `JetBrains Mono` for script text (chunk numbers and pause markers read clearly in mono). Both are bundled locally with the Studio assets; no font CDN, no external calls.
- Scale (px): 12, 14, 16, 18, 22, 28.
  - Player label: 16 (kid variant 22).
  - Time display: 14 (kid 18), with tabular numerals (`font-variant-numeric: tabular-nums`).
  - Caption line: 16 (kid 22).
  - Studio chunk text: 14 mono; Studio section titles: 18 or 22; page title: 28.
- Weights: 400 body, 600 labels and buttons. No weights above 700.
- Line height: 1.4 for UI text, 1.6 for caption line.

---

## 4. Spacing and shape

- 4px base unit: 4, 8, 12, 16, 24, 32, 48.
- Player padding 12 (kid 20).
- Radius: 12 on the card, full circle on the play button, 8 on Studio panels, 999 on pills.
- Shadows: none by default; if any, no heavier than `0 1px 2px rgba(0,0,0,.06)`.
- Borders: 1px `--as-border`.

---

## 5. Signature element: the breathing waveform

A row of **28** slim rounded bars beneath the label, drawn from real peak data in the manifest (precomputed during mastering, embedded as a compact attribute).

- Data: the `peaks` attribute is a comma-separated list of 28 integers, each 0 to 100, e.g. `peaks="12,30,44,61,58,40,...,22"`. Bar height = 8 + (value / 100) * 24 px (min 8 px, max 32 px; kid variant scales by 1.25).
- Bars to the left of the playhead fill with `--as-accent`; bars to the right use `--as-surface-2`.
- The bar at the playhead "breathes" (scale 1.0 to 1.15, 1.6 s ease-in-out infinite loop) only while playing.
- It echoes the "find your calm, take three slow breaths" spirit of the flagship letters.
- Disabled under `prefers-reduced-motion: reduce` (bars still fill with progress, no scale animation).
- Fallback: if `peaks` is missing or malformed, render a flat progress bar (no error shown).
- The waveform is a progress control: click or tap seeks to that position; it exposes `role="slider"` semantics (see Accessibility).

---

## 6. Player states

| State | Trigger | Visuals | Text status |
|---|---|---|---|
| idle | Loaded, not started | Play glyph, waveform unfilled, duration shown | Label (e.g. "Listen") |
| loading | Play pressed, audio buffering | Play button shows a ring only if it lasts over 300 ms | "Loading audio" |
| playing | Audio playing | Pause glyph, bars fill, playhead bar breathes | Elapsed time updates |
| paused | User paused | Play glyph, bars stay filled to position | "Paused" announced to screen readers |
| ended | Playback finished | Replay glyph, waveform fully filled, no breathing | "Finished. Play again" |
| error | Audio or captions failed to load | ErrorState replaces waveform, retry button | "Could not load the audio. Try again" |
| offline | Browser reports no network and audio not buffered | ErrorState variant, retry disabled until online | "You are offline. Audio will play when you are back online" |

Rules:

- Spinners longer than 300 ms must be accompanied by text status.
- Error and offline states never block the rest of the page and never autoplay on recovery.
- Playback position is saved to localStorage inside try/catch; if storage is blocked the player still works.

### 6.1 Captions on and off

- Captions toggle (CC) is shown only when a `captions` track exists.
- Off (default): CaptionLine hidden, toggle `aria-pressed="false"`.
- On: CaptionLine shown below the card, one cue (sentence) at a time, `aria-pressed="true"`. The choice persists as a boolean in localStorage (try/catch), the only other value stored besides position.
- Captions text comes from the narrated script, never from the original page.

### 6.2 Language toggle

- Shown only when `tracks` has more than one entry. Segmented control, e.g. `[EN|HI]`, labels are language codes in uppercase with accessible names ("English", "Hindi").
- Switching language keeps the same relative position when durations are comparable, otherwise restarts at 0:00, and keeps the playing or paused state. Captions switch to the matching VTT.
- The selected language is reflected in the `lang` attribute of CaptionLine.

### 6.3 Kid variant (`size="kid"`)

- Play button 64px (default 44px), label 22px, padding 20, bigger waveform and time.
- Accents `--as-sun` and `--as-sky` may be used for the progress thumb and play ring; the play glyph stays high contrast.
- Layout is vertical: button and label on top row, scrub bar with time below.
- Hit targets never below 64px for the main button and 44px elsewhere.

---

## 7. Wireframes

### 7.1 Player

```
Default
+--------------------------------------------------------------+
|  (>)   Listen to Dad read this letter          4:12   [CC] [EN|HI] |
|        |||||||.|||||.||||||||||||..|||||                       |
+--------------------------------------------------------------+
        (CaptionLine, when captions are on, sits below the card)
        "Today I want to tell you about taking three slow breaths."

Kid variant (size="kid")
+----------------------------------------+
|                                        |
|      (  >  )     Listen to Dad         |
|     64px btn     big friendly label    |
|  [=========o-----------------]  4:12   |
+----------------------------------------+
```

Error state (default size):

```
+--------------------------------------------------------------+
|  (!)   Could not load the audio.                  [Try again]  |
+--------------------------------------------------------------+
```

### 7.2 Studio: script editor with chunk list

```
+----------------------------------------------------------------------------------+
| mr-audio-smith Studio      Project: letter-calm-in-the-chaos     [Render] [Approve] |
+------------------------+---------------------------------------------------------+
| CHUNKS                 | SCRIPT (chunk 3 of 11)                                  |
| [filter: all v]        |                                                         |
| 01 Hello little...  OK | 03  Sometimes the world feels very loud. [pause:short]  |
| 02 Today I want...  OK |     But inside you there is a quiet place. [pause:long] |
| 03 Sometimes th.. STALE|                                                         |
| 04 Take a slow...   OK |  Markers: [pause:short] [pause:long] [emph]...          |
| 05 Breathe in...  DRAFT|                                                         |
| ...                    |  Validation: 0 errors, 1 warning (long sentence)        |
+------------------------+---------------------------------------------------------+
| Time: 4:12 est.   Chunks: 11   Stale: 1   Failed: 0                              |
+----------------------------------------------------------------------------------+
```

### 7.3 Studio: chunk detail with take comparison

```
+----------------------------------------------------------------------------------+
| Chunk 03   Status: [STALE]   Voice: dad-v1   Seed: 4271                          |
+----------------------------------------------------------------------------------+
| Text: Sometimes the world feels very loud. ...                                   |
+-------------------------------------+--------------------------------------------+
| TAKE A (kept)       sim 0.84        | TAKE B               sim 0.79              |
| [> play]  0:06  ||||||||.|||||||    | [> play]  0:07  |||||.||||||||||            |
| seed 4271                           | seed 9183                                  |
| [Keep A]                            | [Keep B]  [Re-render with new seed]        |
+-------------------------------------+--------------------------------------------+
| Lexicon hits: none           Pronunciation overrides: [+ add]                    |
+----------------------------------------------------------------------------------+
```

### 7.4 Studio: render queue

```
+----------------------------------------------------------------------------------+
| RENDER QUEUE                                                      [Pause] [Clear]|
+----------------------------------------------------------------------------------+
| #  Target            Stage        Progress          Status       ETA             |
| 1  chunk 03          synth        [#######---] 70%  RENDERING    0:08            |
| 2  chunk 05          queued       [----------]  0%  QUEUED       0:20            |
| 3  chunk 06          queued       [----------]  0%  QUEUED       0:28            |
| 4  chunk 02          qa           [##########] 100% FAILED       Retry (1 of 2)  |
+----------------------------------------------------------------------------------+
```

### 7.5 Studio: approve and publish panel

```
+----------------------------------------------------------------------------------+
| APPROVE AND PUBLISH                                                              |
+----------------------------------------------------------------------------------+
| Master preview:  [> play]  4:12   -16.1 LUFS   -2.0 dBTP     OK                  |
| Voice similarity: mean 0.82 (min 0.76, threshold 0.75)       OK                  |
| Chunks: 11 rendered, 0 stale, 0 failed                       OK                  |
| Outputs:  letter.mp3  letter.vtt  letter.manifest.json  letter.embed.html        |
| Diff vs published:  [View diff]  (2 files changed)                               |
|                                                                                  |
|  [ ] I have listened to this narration and approve it.                           |
|  [Approve and publish]    [Cancel]                                               |
+----------------------------------------------------------------------------------+
```

---

## 8. Component inventory

### 8.1 Player components

| Component | Props / attributes | States | Notes |
|---|---|---|---|
| PlayButton | `state` (idle, loading, playing, paused, ended), `size` (default 44px, kid 64px), `label` for accessible name | default, hover, active, focus-visible, loading, disabled | Round, `--as-accent` fill, glyph swaps play, pause, replay. Accessible name changes with state |
| Label | `text` (default "Listen") | default, truncated (ellipsis with full text in `title`) | 16px (kid 22px), weight 600 |
| Waveform | `peaks` (28 ints 0-100), `progress` (0-1), `playing` (bool), `reducedMotion` (bool) | empty (flat bar fallback), progress, breathing, reduced-motion | `role="slider"`, `aria-valuemin/max/now`, click and keyboard seek |
| Time | `current`, `duration`, `mode` (elapsed, remaining) | idle (duration only), running, unknown duration (shows "--:--") | Tabular numerals; announced politely on pause, not every second |
| CaptionsToggle | `available` (bool), `pressed` (bool) | hidden, off, on, focus-visible | `aria-pressed`; hidden when no captions track |
| LanguageToggle | `tracks` (array of code and name), `selected` | hidden (single track), default, selected, focus-visible | Segmented, `role="radiogroup"` |
| CaptionLine | `text`, `lang`, `visible` | hidden, showing, empty cue | `aria-live="off"` by default so it does not double-read native audio; sits below the card |
| ErrorState | `kind` (error, offline), `message`, `onRetry` | error, offline (retry disabled), retrying | `role="alert"`; no emoji; plain sentence plus Retry button |

### 8.2 Studio components

| Component | Props | States | Notes |
|---|---|---|---|
| ProjectList | `projects` (slug, title, updated, status), `onOpen` | empty ("No projects yet. Run mr-audio-smith narrate <url>"), loading, list, error | Left rail or landing page |
| ChunkList | `chunks`, `selectedId`, `filter` (all, stale, failed), `onSelect` | empty, loading, list, filtered-empty | Keyboard navigable (up and down), virtualized above 200 chunks |
| ChunkRow | `index`, `snippet`, `status` (draft, stale, rendering, rendered, approved, failed), `durationMs` | default, selected, hover, focus-visible | Status pill: text plus color, never color alone |
| ChunkEditor | `text`, `markers`, `violations`, `onChange`, `onRender` | pristine, dirty, invalid (violations listed with chunk numbers), saving | Mono font; live validation using the same rules as FR-006 |
| MarkerChip | `kind` (pause:short, pause:long, emph), `onInsert`, `onRemove` | default, selected, disabled (unknown marker rejected) | Inserts only allowed markers |
| TakeCompare | `takes` (id, seed, similarity, audioUrl), `kept`, `onKeep`, `onRerender` | single take, two takes, no takes, rendering, keeping | Side by side; A and B play buttons; low similarity flagged in text |
| RenderQueue | `jobs` (target, stage, progress, status, eta), `onPause`, `onRetry`, `onClear` | empty, running, paused, has-failures | Per-job status text: Queued, Rendering, Rendered, Failed |
| MasterPreview | `audioUrl`, `loudness`, `truePeak`, `duration` | not-ready, ready, out-of-spec (loudness or peak off target, shown in text) | Plays the mastered file; shows measured vs target values |
| ApprovePanel | `checks` (list of ok/blocked), `outputs`, `onApprove` | blocked (stale or failed chunks), ready, approving, approved | Approve disabled until checkbox is ticked and checks pass |
| DiffViewer | `before`, `after`, `kind` (script, manifest, html) | empty (no changes), unified diff, split diff | Used for script edits and inject dry-run |
| Toast | `kind` (info, success, error), `message`, `durationMs` | entering, visible, leaving | `role="status"` (error: `role="alert"`); auto-dismiss 5 s, errors persist until dismissed |

---

## 9. Player attribute contract

`<audio-smith-player>` is configured through HTML attributes. All values are strings.

| Attribute | Required | Type / format | Default | Description |
|---|---|---|---|---|
| `src` | yes | URL | none | Default audio track (MP3 or Opus) |
| `captions` | no | URL | none | WebVTT file for the default track |
| `label` | no | text | `Listen` | Visible label and accessible name base |
| `size` | no | `default` or `kid` | `default` | `kid` gives a 64px play button, larger label |
| `tracks` | no | JSON array string, e.g. `[{"lang":"en","name":"English","src":"a.mp3","captions":"a.vtt"},{"lang":"hi","name":"Hindi","src":"a.hi.mp3","captions":"a.hi.vtt"}]` | none | Extra language tracks; the toggle appears when more than one track exists |
| `theme` | no | `auto`, `light`, `dark` | `auto` | Maps to `data-theme` handling in section 2 |
| `peaks` | no | 28 comma-separated integers 0 to 100 | none (flat bar) | Precomputed waveform from mastering |
| `download` | no | boolean attribute | absent | Opt-in only: shows a download link. Never present by default |
| `debug` | no | boolean attribute | absent | Logs state transitions to the console; never sends anything off-page |

Rules:

- Invalid JSON in `tracks` is ignored with a console warning and the player falls back to `src`.
- The element renders a plain `<audio controls src=...>` as light-DOM fallback content so the page works with JavaScript disabled. The component hides the fallback when it upgrades.
- Events emitted: `as-play`, `as-pause`, `as-ended`, `as-error`, `as-language` (detail: `{lang}`), all bubbling, no data leaves the page.
- No network requests other than the declared audio and captions URLs.

Example:

```html
<audio-smith-player
  src="letter-calm-in-the-chaos.mp3"
  captions="letter-calm-in-the-chaos.vtt"
  label="Listen to Dad read this letter"
  size="kid"
  peaks="12,30,44,61,58,40,35,52,70,66,48,39,28,33,47,59,72,64,50,41,36,30,26,34,45,38,24,15"
  tracks='[{"lang":"en","name":"English","src":"l.mp3","captions":"l.vtt"},{"lang":"hi","name":"Hindi","src":"l.hi.mp3","captions":"l.hi.vtt"}]'>
  <audio controls src="letter-calm-in-the-chaos.mp3"></audio>
</audio-smith-player>
```

---

## 10. Keyboard map

| Key | Action | Condition |
|---|---|---|
| Space or K | Play or pause | Focus anywhere inside the player |
| Left arrow | Seek back 5 s | Focus on the waveform or player |
| Right arrow | Seek forward 5 s | Focus on the waveform or player |
| C | Toggle captions | Only when a captions track exists |
| L | Switch to the next language | Only when more than one track exists |
| Tab / Shift+Tab | Move through PlayButton, Waveform, CaptionsToggle, LanguageToggle | Visible focus ring on each |
| Home / End | Jump to start or end | Focus on the waveform |

Rules: shortcuts act only when focus is inside the player, so they never hijack page-level keys. Up and Down arrows are not captured (page scrolling is preserved). On mobile there is no volume slider; the device volume is used.

Studio keyboard additions: Up and Down move through ChunkList, Enter opens a chunk, `Ctrl/Cmd+Enter` renders the selected chunk, `Esc` closes dialogs.

---

## 11. Motion rules

- Exactly one continuous animation: the waveform breathing, only while playing.
- Breathing: scale 1.0 to 1.15, 1.6 s, ease-in-out, infinite alternate, applied to one bar.
- Transitions for hover, press, and toggle: 120 ms ease-out on color and opacity only.
- Toast: 160 ms fade and 8px slide; no bounce.
- Under `prefers-reduced-motion: reduce`: no breathing, no slide, transitions reduced to instant color changes; progress still updates.
- Nothing flashes more than three times per second.
- Spinners over 300 ms must be paired with text.

---

## 12. Accessibility (WCAG 2.2 AA)

- Fully keyboard operable (section 10), visible focus ring: 2px outline `--as-focus` with 2px offset, never removed.
- Contrast: body text at least 4.5:1, large text and UI components at least 3:1, in both light and dark.
- Target size: at least 44 by 44 CSS px for every interactive control; kid play button 64px. Spacing between targets at least 8px.
- Semantics: PlayButton is a `button` with state-based name ("Play", "Pause", "Replay"); Waveform is `role="slider"` with `aria-valuetext` like "1 minute 20 seconds of 4 minutes 12 seconds"; toggles use `aria-pressed`; language toggle uses `radiogroup`.
- Captions available as WebVTT; CaptionLine is readable text, not an image.
- Status changes (loading, error, offline) announced through a polite live region; errors use `role="alert"`.
- Not color alone: Studio chunk status uses a text pill; player error uses text and an icon shape.
- Reduced motion respected (section 11); no autoplay; no seizure-risk flashing.
- Text resizes to 200 percent without loss of function; layout reflows at 320 CSS px width.
- Pointer gestures are single-tap or click only (no drag-only controls; seeking also works with keys and tap).
- Studio: all screens operable by keyboard, landmarks and headings present, forms labeled, toasts do not steal focus.

---

## 13. Copy guidelines

- Player label defaults to "Listen". Authors may override, e.g. "Listen to Dad read this letter".
- Tone: plain, warm, short sentences. Address the listener directly. Never baby-talk, never marketing speak.
- Sentence case for all UI text. No exclamation marks. No emoji anywhere in the player UI.
- Error copy says what happened and what to do next: "Could not load the audio. Try again." Offline: "You are offline. Audio will play when you are back online."
- Time shown as `m:ss` (4:12); screen reader text spells it out.
- Language buttons show uppercase codes (EN, HI) with full names as accessible names.
- Studio copy is direct and technical but never blaming: "Chunk 3 is stale. Re-render to hear your edit."
- No brand watermark, no "powered by" text in the player.

---

## 14. Anti-patterns (must not appear)

- Autoplay of any kind
- Gradients, glassmorphism, drop shadows heavier than `0 1px 2px rgba(0,0,0,.06)`
- Emoji inside the player UI
- Volume sliders on mobile (use device volume)
- Tiny touch targets under 44px (under 64px for the kid play button)
- Download buttons by default (opt-in attribute only)
- Brand watermarks or "powered by" badges in the player
- Spinners longer than 300 ms without a text status
- Color as the only signal for chunk status in Studio (always pair with a text pill)
- External fonts, scripts, analytics, or network calls from the player or Studio
- Hijacking page-level keyboard shortcuts or scroll
- Animations beyond the single breathing waveform

## Implementation notes (Sprint 4, recorded from the built player)

- Space on a focused button is left to the browser's native activation (no double toggle); Space elsewhere in the player and K anywhere toggle playback.
- A captions fetch failure hides the CC toggle and emits an `as-error` event with `kind: "captions"`; audio keeps playing and the player does not enter the error state.
- `tracks` entries accept `label` or `name` and fall back to the uppercased language code. The active track defaults to the one whose `src` matches the `src` attribute.
- Switching language keeps the relative position only when the new track's duration is within 15 percent of the old one; otherwise it restarts at 0:00.
- A saved position is restored only when it is at least 1 second in.
- The CC button reads "CC"; `captions-on-label` and `captions-off-label` override it; pressed state is conveyed by `aria-pressed`.
- Optional `artist` attribute feeds Media Session metadata.
- Measured bundle: about 6.5 KB gzipped (NFR-011 limit 12 KB).
