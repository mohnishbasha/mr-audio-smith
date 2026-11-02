# Python API

The public surface is `audio_smith.api`. The top-level shortcut `audio_smith.narrate(...)` imports it
lazily, so `import audio_smith` stays fast.

```python
import audio_smith

result = audio_smith.narrate(
    "letter.html",
    profile="kid-5",
    voice="dad",
    backend="maya2",
    inject=None,
)
print(result)
```

Every function raises a typed `AudioSmithError` subclass (see the
[exit codes](cli.md#exit-codes)) with a code, a stage, and a hint.

## audio_smith.api

::: audio_smith.api

## audio_smith.orchestrate.narrate

::: audio_smith.orchestrate.narrate
