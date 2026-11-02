#!/usr/bin/env bash
set -euo pipefail
NEW="${1:?Usage: $0 <new-version>}"
[[ "$NEW" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-rc\.[0-9]+)?$ ]] || { echo "Invalid semver: $NEW"; exit 2; }
cd "$(git rev-parse --show-toplevel)"
uv version "$NEW"   # updates pyproject.toml (verify flag name for the installed uv version)
for f in player/package.json integrations/pi/package.json web/studio/package.json; do
  tmp=$(mktemp); jq --arg v "$NEW" '.version=$v' "$f" > "$tmp" && mv "$tmp" "$f"
done
yq -i ".version = \"$NEW\" | .appVersion = \"$NEW\"" charts/mr-audio-smith/Chart.yaml
yq -i ".inputs.image-tag.default = \"$NEW\"" action/action.yml
./scripts/check-versions.sh
