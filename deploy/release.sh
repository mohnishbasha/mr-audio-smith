#!/usr/bin/env bash
# Release helpers for the Flux flow (see `make release`). Run from anywhere; paths resolve from this file.
#
#   deploy/release.sh published        exit 0 if the chart version in Chart.yaml is already in the registry,
#                                      1 if it is not, 2 if the registry could not be checked
#   deploy/release.sh pin <image-tag>  in $DEPLOY_REPO: branch snackonai/<app>-<tag>, pin this app's chart + image
#                                      in fleet.yaml (ENABLE=1 also sets enabled: true), run render/render.py,
#                                      commit; prints the gh pr create command. `home:` on the line is never touched;
#                                      IMAGE_HOME (the unit the image was imported on, `deploy.sh --home`) must equal it.
#                                      The Maya TTS image needs no fleet pin: the chart's maya.image.tag
#                                      default is the short MAYA_REF baked into Dockerfile.maya, and deploy.sh --image
#                                      builds + imports maya-tts:<that tag> next to the app image.
#
# Env: ENABLE (1 = also set enabled: true on the app's line), IMAGE_HOME (required by pin when the line has home:), HELM (default helm),
#      DEPLOY_REPO (default ../../stokeai-deploy from the app dir),
#      CHART_REPO (default oci://ghcr.io/mohnishbasha/charts), FLEET_FILE (default $DEPLOY_REPO/fleet.yaml).
# Never pushes and never opens a PR. The stokeai-deploy commit carries no attribution trailer (its rules forbid them).
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP="$(basename "$APP_DIR")"
CHART_DIR="$APP_DIR/charts/$APP"
HELM="${HELM:-helm}"
CHART_REPO="${CHART_REPO:-oci://ghcr.io/mohnishbasha/charts}"
DEPLOY_REPO="${DEPLOY_REPO:-$APP_DIR/../../stokeai-deploy}"
version="$(sed -n 's/^version: *"\{0,1\}\([^"]*\)"\{0,1\} *$/\1/p' "$CHART_DIR/Chart.yaml" | head -1)"

case "${1:-}" in
  published)
    if out=$($HELM show chart "$CHART_REPO/$APP" --version "$version" 2>&1); then
      exit 0
    elif echo "$out" | grep -qiE 'not found|404|manifest unknown|no such'; then
      exit 1
    else
      echo "$out" >&2
      echo "could not check $CHART_REPO/$APP:$version. Log in first: helm registry login ghcr.io -u <github-user>" >&2
      echo "(password: a gh token with write:packages, e.g. gh auth refresh -s write:packages; gh auth token)" >&2
      exit 2
    fi
    ;;
  pin)
    tag="${2:?usage: release.sh pin <image-tag>}"
    # fleet.yaml only accepts a clean git sha (hex, 7-40 chars): never a -dirty-<ts> build.
    echo "$tag" | grep -Eq '^[0-9a-f]{7,40}$' \
      || { echo "refusing to pin image tag '$tag': commit first (fleet.yaml takes only a clean git sha)" >&2; exit 1; }
    [ -e "$DEPLOY_REPO/.git" ] || { echo "no deploy repo at $DEPLOY_REPO (set DEPLOY_REPO=)" >&2; exit 1; }
    DEPLOY_REPO="$(cd "$DEPLOY_REPO" && pwd)"
    FLEET_FILE="${FLEET_FILE:-$DEPLOY_REPO/fleet.yaml}"
    [ -f "$FLEET_FILE" ] || { echo "no fleet file at $FLEET_FILE (set FLEET_FILE=)" >&2; exit 1; }
    [ -z "$(git -C "$DEPLOY_REPO" status --porcelain)" ] \
      || { echo "$DEPLOY_REPO has uncommitted changes; clean it first" >&2; exit 1; }
    # The image only exists on the unit it was built on: that must be the line's `home:` (Flux runs the app there).
    line_home="$(sed -n -E "s/^[[:space:]]*$APP:[[:space:]]*\\{.*[{, ]home:[[:space:]]*\"?([A-Za-z0-9._-]+)\"?.*/\\1/p" "$FLEET_FILE" | head -1)"
    if [ -n "$line_home" ]; then
      [ -n "${IMAGE_HOME:-}" ] || { echo "refusing to pin: set IMAGE_HOME to the unit the image was imported on (deploy/deploy.sh --home); the fleet line says home: $line_home" >&2; exit 1; }
      [ "$IMAGE_HOME" = "$line_home" ] \
        || { echo "refusing to pin: the image was imported on $IMAGE_HOME but $APP's fleet line says home: $line_home. Rebuild with HOME_UNIT=$line_home, or change home: in stokeai-deploy first." >&2; exit 1; }
    fi
    python3 -c 'import yaml' 2>/dev/null \
      || { echo "render/render.py needs PyYAML: python3 -m pip install --user pyyaml" >&2; exit 1; }
    branch="snackonai/$APP-$tag"
    git -C "$DEPLOY_REPO" checkout -b "$branch"
    ENABLE="${ENABLE:-}" APP="$APP" CHART_VERSION="$version" IMAGE_TAG="$tag" FLEET_FILE="$FLEET_FILE" python3 - <<'PY'
import os, re, sys
app, chart, image, path = os.environ["APP"], os.environ["CHART_VERSION"], os.environ["IMAGE_TAG"], os.environ["FLEET_FILE"]
enable = bool(os.environ.get("ENABLE"))
lines = open(path).read().split("\n")
pat = re.compile(r"^(\s*%s:\s*\{)(.*)(\}.*)$" % re.escape(app))
hit = 0
for i, line in enumerate(lines):
    m = pat.match(line)
    if not m:
        continue
    body = m.group(2)
    for key, val in (("chart", chart), ("image", image)):
        if re.search(r"\b%s:" % key, body):
            body = re.sub(r"\b%s:\s*(\"[^\"]*\"|'[^']*'|[^,}\s]*)" % key, '%s: "%s"' % (key, val), body)
        else:
            body = body.rstrip() + ', %s: "%s"' % (key, val)
    if enable:
        if re.search(r"\benabled:", body):
            body = re.sub(r"\benabled:\s*[^,}\s]*", "enabled: true", body)
        else:
            body = "enabled: true, " + body.lstrip()
    lines[i] = m.group(1) + body + m.group(3)
    hit += 1
if hit != 1:
    sys.exit("expected exactly one '%s: {...}' line in %s, found %d" % (app, path, hit))
homes = lambda text: re.findall(r"\bhome:\s*\S+?(?=[,}\s])", text)
if homes("\n".join(lines)) != homes(open(path).read()):
    sys.exit("internal error: home changed; refusing to write")
open(path, "w").write("\n".join(lines))
PY
    (cd "$DEPLOY_REPO" && python3 render/render.py)
    git -C "$DEPLOY_REPO" add -A
    git -C "$DEPLOY_REPO" commit -q -m "snackonai: $APP chart $version, image $tag${ENABLE:+ (enable)}"
    echo
    echo "committed on branch $branch in $DEPLOY_REPO"
    git -C "$DEPLOY_REPO" show --stat --format= HEAD
    echo "next (not run for you):"
    echo "  cd $DEPLOY_REPO && git push -u origin $branch && gh pr create --fill"
    ;;
  *)
    sed -n '2,13p' "$0" >&2
    exit 64
    ;;
esac
