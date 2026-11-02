---
name: narrate-page
description: Narrate a web page or local HTML/Markdown file into an MP3 with captions and a player embed using mr-audio-smith. Use when the user asks to narrate, read aloud, make an audio version, or add a "Listen" player to a page or letter.
---

# Narrate a page with mr-audio-smith

## When to use
The user wants an audio version of a page: "narrate this letter for my kid", "make a listen
button for this post", "read this page in my voice", "add audio to every letter on my site".

## Rules
- Cloned voices need a consent record. Never try to clone a voice that is not registered. If
  `mr_audio_smith_list_voices` does not show the voice, tell the user to run
  `mr-audio-smith voice add <id> --clip <wav> --name "<speaker>" --relationship self` themselves
  (only their own voice or one they have written permission to use).
- Do not invent capabilities: there are no emotion tags. Warmth comes from the script wording.
- Never edit the user's HTML outside the `<!-- audio-smith:start -->` and `<!-- audio-smith:end -->` markers.

## Steps
1. Pick a profile: call `mr_audio_smith_recommend` with the page or the user's description, or use
   `kid-5` for young children, `adult-brief` for summaries, `adult-commute` for long listens.
2. Review before rendering when the user cares about wording: call `mr_audio_smith_script`, show
   the script path and a short excerpt, and apply the user's edits to the Markdown file (only
   `## NNN` headings, `[pause N]`, and `*word*` are allowed).
3. Narrate: `mr_audio_smith_narrate` with `source`, `profile`, `voice`, and optional `langs`
   (for example `["en", "hi"]`). For an edited script use `mr_audio_smith_render` instead.
4. Report the MP3, captions, and embed paths, the duration, and any warnings (for example low
   voice similarity on a chunk, which the user can fix in `mr-audio-smith studio`).
5. For a static site: pass `inject_path` with the local HTML file to add the player, or run
   `mr-audio-smith site <index-url> --match "letter-*.html" --inject-root <site-dir>` for a batch.

## Without the MCP server
The CLI does the same: `mr-audio-smith run <url> --profile kid-5 --voice dad --inject page.html`.
