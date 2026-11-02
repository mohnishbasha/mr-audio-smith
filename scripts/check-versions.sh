#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

CANONICAL=$(python3 - <<'PY'
import tomllib
with open("pyproject.toml", "rb") as f:
    print(tomllib.load(f)["project"]["version"])
PY
)

check() {
  local actual=$1 file=$2
  if [[ "$actual" != "$CANONICAL" ]]; then
    echo "✗ Version mismatch in $file: expected $CANONICAL, got $actual"
    exit 1
  fi
  echo "✓ $file: $CANONICAL"
}

check "$(jq -r '.version' player/package.json)" "player/package.json"
check "$(jq -r '.version' integrations/pi/package.json)" "integrations/pi/package.json"
check "$(jq -r '.version' web/studio/package.json)" "web/studio/package.json"
check "$(yq -r '.version' charts/mr-audio-smith/Chart.yaml)" "charts/mr-audio-smith/Chart.yaml (version)"
check "$(yq -r '.appVersion' charts/mr-audio-smith/Chart.yaml)" "charts/mr-audio-smith/Chart.yaml (appVersion)"
check "$(yq -r '.inputs.image-tag.default' action/action.yml)" "action/action.yml (image-tag)"

echo "── All versions consistent: $CANONICAL ──"
