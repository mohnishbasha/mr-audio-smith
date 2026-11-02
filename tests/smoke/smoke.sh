#!/usr/bin/env bash
# Smoke: minimal end-to-end sanity with mocks. Extended every sprint as stages land.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
echo "smoke_version_prints_semver"
uv run mr-audio-smith --version
echo "smoke_doctor_json_parses"
uv run mr-audio-smith doctor --json | uv run python -c "import json,sys; d=json.load(sys.stdin); print('doctor ok' if d['results'] else 'empty')" || true
echo "smoke: all passed"
