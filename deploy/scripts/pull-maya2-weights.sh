#!/bin/sh
# Pre-download the Maya 2 weights into the models volume and optionally verify them, so the first
# `maya2` start needs no network. Used by the compose `maya2-pull` service. The Helm chart carries the same
# logic inline in its maya2 init container.
#   MAYA_WEIGHTS_REPO       default maya-research/maya2-native
#   MAYA_WEIGHTS_REVISION   default main; pin a commit sha for reproducible installs
#   MAYA_WEIGHTS_SHA256SUMS optional path to a `sha256sum` file (paths relative to the snapshot dir)
set -eu
REPO="${MAYA_WEIGHTS_REPO:-maya-research/maya2-native}"
REV="${MAYA_WEIGHTS_REVISION:-main}"
export HF_HOME="${HF_HOME:-/models/hf-cache}"
mkdir -p "$HF_HOME"
if command -v huggingface-cli >/dev/null 2>&1; then
  DL="huggingface-cli download"
else
  DL="hf download"
fi
echo "pulling $REPO@$REV into $HF_HOME"
SNAP="$($DL "$REPO" --revision "$REV" | tail -n 1)"
if [ -n "${MAYA_WEIGHTS_SHA256SUMS:-}" ] && [ -f "$MAYA_WEIGHTS_SHA256SUMS" ]; then
  echo "verifying checksums from $MAYA_WEIGHTS_SHA256SUMS"
  (cd "$SNAP" && sha256sum -c "$MAYA_WEIGHTS_SHA256SUMS")
else
  echo "no checksum file provided; skipping verification (set MAYA_WEIGHTS_SHA256SUMS to enable)"
fi
echo "weights ready: $SNAP"
