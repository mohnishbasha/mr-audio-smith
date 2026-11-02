#!/usr/bin/env bash
# Smoke: minimal end-to-end sanity with the fake LLM and mock TTS (no network, no GPU).
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
OUT="$(mktemp -d)"
export AUDIO_SMITH_CACHE_DIR="$OUT/cache"
echo "smoke_version_prints_semver"
uv run mr-audio-smith --version
echo "smoke_doctor_json_parses"
uv run mr-audio-smith doctor --json | uv run python -c "import json,sys; d=json.load(sys.stdin); assert d['results']" || true
echo "smoke_run_mock_outputs_exist"
uv run mr-audio-smith run tests/fixtures/pages/letter-calm.html --llm fake --backend mock --out "$OUT/out"
for f in letter-calm.mp3 letter-calm.vtt letter-calm.manifest.json; do test -s "$OUT/out/letter-calm/$f"; done
echo "smoke_manifest_validates_schema"
uv run python -c "import json,sys,jsonschema; jsonschema.validate(json.load(open(sys.argv[1])), json.load(open('schemas/manifest.schema.json')))" "$OUT/out/letter-calm/letter-calm.manifest.json"
echo "smoke_unchanged_rerun_is_cached"
RERUN="$(uv run mr-audio-smith run tests/fixtures/pages/letter-calm.html --llm fake --backend mock --out "$OUT/out")"
grep -q "(cached)" <<<"$RERUN"
echo "smoke: all passed"
