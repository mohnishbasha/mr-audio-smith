#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
uv run mr-audio-smith run tests/fixtures/pages/letter-calm.html --llm fake --backend mock --out out --force
uv run python -c "import json,jsonschema; jsonschema.validate(json.load(open('out/letter-calm/letter-calm.manifest.json')), json.load(open('schemas/manifest.schema.json')))"
ls out/letter-calm/*.mp3 out/letter-calm/*.vtt out/letter-calm/*.embed.html
