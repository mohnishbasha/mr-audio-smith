# Site mode

`site` narrates every page linked from an index page, in one run, with one loaded voice model.

```bash
mr-audio-smith site https://example.com/letters.html --match "letter-*.html" \
  --profile kid-5 --voice dad
```

## How it works

1. Fetch the index page and collect its links.
2. Keep links on the same origin whose file name matches `--match` (a glob such as `letter-*.html`).
3. Narrate each page, up to `--max-pages` (default 50). Unchanged pages report `cached` and render
   nothing, so a nightly run only does new work.
4. Print a table of page, status (`rendered`, `cached`, or `failed`), duration, and a note.

One bad page never sinks the batch. If any page failed, the command exits 6 after finishing the rest.

## Injecting players into a local checkout

Pass `--inject-root` with your static site directory and `site` adds the player to each matching
local file, between the audio-smith markers:

```bash
mr-audio-smith site https://www.example.com/messages.html --match "letter-*.html" \
  --inject-root . --selector h1 --out media/audio
```

`--selector` says where the markers go for a page that does not have them yet (default: after the
`h1`). Everything outside the markers is left byte for byte as you wrote it.

## Working from local files

The index can be a local file too (use `--allow-private` if the pages come from a private host).
Combine it with `--backend mock --llm fake` to rehearse a site without models.

## Tips

- Set `default_profile`, `default_voice`, `out_dir`, and the `embed_*` settings in `audio-smith.toml`
  so the command line stays short. See [Configuration](configuration.md).
- Mark what to read with `data-narrate` attributes. See [Embedding](embedding.md) and
  [Profiles](profiles.md) for the markup and parent track.
- Use `--force` to ignore the cache and re-render everything.
- To run this on every push, use the [GitHub Action](github-action.md).
