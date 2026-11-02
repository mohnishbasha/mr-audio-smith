#!/usr/bin/env bash
set -euo pipefail
NEW="${1:?Usage: $0 <new-version>}"
[[ "$NEW" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-rc\.[0-9]+)?$ ]] || { echo "Invalid semver: $NEW"; exit 2; }
cd "$(git rev-parse --show-toplevel)"
# Write the semver string literally: `uv version` would normalize 1.0.0-rc.1 to PEP 440 1.0.0rc1
# and break the comparison with package.json and Chart.yaml (PEP 440 accepts the semver form).
python3 - "$NEW" <<'PY'
import re, sys
from pathlib import Path
p = Path("pyproject.toml")
text = p.read_text(encoding="utf-8")
p.write_text(re.sub(r'(?m)^version = "[^"]*"', f'version = "{sys.argv[1]}"', text, count=1), encoding="utf-8")
PY
uv lock -q
for f in player/package.json integrations/pi/package.json web/studio/package.json; do
  tmp=$(mktemp); jq --arg v "$NEW" '.version=$v' "$f" > "$tmp" && mv "$tmp" "$f"
done
# Only appVersion: the chart `version` is its own semver, bumped by hand when the chart changes.
yq -i ".appVersion = \"$NEW\"" charts/mr-audio-smith/Chart.yaml
yq -i ".inputs.image-tag.default = \"$NEW\"" action/action.yml
./scripts/check-versions.sh
