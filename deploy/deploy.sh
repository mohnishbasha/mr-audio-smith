#!/usr/bin/env bash
# Deploy mr-audio-smith.openstoke.com to the StokeAI DGX Spark platform.
#
# LEGACY direct apply (before Flux). Flux GitOps rolls the cluster out from stokeai-deploy; use
# `make release` (which calls `deploy.sh --image`) for that. Plain `deploy.sh` keeps working, but refuses
# to touch a namespace Flux owns (see the HelmRelease guard below).
#
# Build the image on the home unit, import it into k3s (there is no registry for our own images), apply the
# Helm chart there, and put a stand-in Service plus the route in the other platform clusters so whichever
# platform machine a tailnet client lands on can route to it. Run from a Mac on the tailnet that can ssh to
# the units as `stoke`.
#
#   deploy/deploy.sh                 # build, import, apply, routes, wait, smoke test
#   deploy/deploy.sh --routes        # only the stand-ins and routes
#   deploy/deploy.sh --image         # preflight, copy, build on the home unit, import into k3s, prune; prints the tag
#                                    # (also builds + imports maya-tts:<short MAYA_REF>-r<rev> from Dockerfile.maya2 unless
#                                    # that tag is already imported: it is big, ~10 GB, so it is built once per ref)
#   deploy/deploy.sh --home          # only print the home unit and why (no network)
#   deploy/deploy.sh --maya          # only the Maya TTS image (preflight, copy, build + import unless already imported)
#   deploy/deploy.sh --tag           # only print the image tag this tree would build (no network)
#   deploy/deploy.sh --check         # only the preflight: Tailscale, the six units, ssh
#   deploy/deploy.sh --clean         # delete what the legacy deploy applied (keeps the PVCs; PURGE=1 deletes them too)
#   SKIP_PREFLIGHT=1 deploy/deploy.sh   # skip the preflight (not recommended)
#   FORCE=1 deploy/deploy.sh         # apply/clean even though a Flux HelmRelease owns the app (can fight Flux: avoid)
#   HOME_UNIT=spark-bundle2-1 deploy/deploy.sh   # overrides fleet.yaml's home: for this app (default spark-bundle2-1)
#   MAYA_REF=<git tag|sha> deploy/deploy.sh --image   # another maya2-native ref (default: ARG MAYA_REF in Dockerfile.maya2)
#   MAYA_IMAGE_REV=2 deploy/deploy.sh --image         # another image revision of the same ref (ARG MAYA_IMAGE_REV)
#   SKIP_MAYA=1 deploy/deploy.sh --image              # do not build the Maya TTS image
#   PLATFORM_UNITS="spark-bundle1-1 spark-bundle2-1 spark-bundle3-1" deploy/deploy.sh   # short ssh aliases
#   HELM_EXTRA="--set replicaCount=1" deploy/deploy.sh
#
# The server token lives in Bao at secret/stoke/mr-audio-smith (property server_token) and reaches the pod
# through an ExternalSecret (see charts/mr-audio-smith/values-openstoke.yaml).
set -euo pipefail

# Tailnet machine names (MagicDNS). Override if your ssh config uses short aliases.
# HOME_UNIT (runs the app and keeps its PVCs) is resolved below, once APP_DIR is known.
read -r -a PLATFORM <<< "${PLATFORM_UNITS:-spark-bundle1-1-7229 spark-bundle2-1 spark-bundle3-1-763e}"  # Envoy for *.openstoke.com
# Every DGX Spark unit on the tailnet; the preflight reports all of them, and requires HOME_UNIT + PLATFORM.
read -r -a FLEET <<< "${FLEET_UNITS:-spark-bundle1-1-7229 spark-bundle1-2-720e spark-bundle2-1 spark-bundle2-2 spark-bundle3-1-763e spark-bundle3-2-7782}"
# Same namespace for the legacy path and Flux, so the two never share one with another app.
NAMESPACE=mr-audio-smith
RELEASE=mr-audio-smith
HOST=mr-audio-smith.openstoke.com
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# Home unit: HOME_UNIT env, else the `home:` on this app's line in $DEPLOY_REPO/fleet.yaml (the stokeai-deploy
# source of truth: {enabled: false, home: <unit>, chart: "x", image: "y"}), else the default for this app.
DEPLOY_REPO="${DEPLOY_REPO:-$APP_DIR/../../stokeai-deploy}"
FLEET_FILE="${FLEET_FILE:-$DEPLOY_REPO/fleet.yaml}"
DEFAULT_HOME_UNIT=spark-bundle2-1
fleet_home() {
  [ -f "$FLEET_FILE" ] || return 0
  sed -n -E "s/^[[:space:]]*$RELEASE:[[:space:]]*\{.*[{, ]home:[[:space:]]*\"?([A-Za-z0-9._-]+)\"?.*/\1/p" "$FLEET_FILE" | head -1
}
if [ -n "${HOME_UNIT:-}" ]; then
  HOME_WHY="HOME_UNIT env"
elif [ -n "$(fleet_home)" ]; then
  HOME_UNIT="$(fleet_home)"; HOME_WHY="home: on the $RELEASE line of $FLEET_FILE"
else
  HOME_UNIT="$DEFAULT_HOME_UNIT"; HOME_WHY="built-in default (no home: for $RELEASE in $FLEET_FILE)"
fi
CHART="$APP_DIR/charts/mr-audio-smith"
APP_DOCKERFILE=deploy/docker/Dockerfile.cpu
MAYA_DOCKERFILE=deploy/docker/Dockerfile.maya2
SRC_DIR=/tmp/mr-audio-smith-src
KUBE='KUBECONFIG=/etc/rancher/k3s/k3s.yaml kubectl'
HELM_EXTRA="${HELM_EXTRA:-}"
FORCE="${FORCE:-}"
PURGE="${PURGE:-}"
# Maya 2 Native TTS image: the single source of the pinned ref is ARG MAYA_REF in Dockerfile.maya2.
# The tag is <first 7 of MAYA_REF>-r<MAYA_IMAGE_REV> (the chart's maya2.image.tag in values-openstoke.yaml).
MAYA_REF="${MAYA_REF:-$(sed -n 's/^ARG MAYA_REF=//p' "$APP_DIR/$MAYA_DOCKERFILE" 2>/dev/null | head -1)}"
MAYA_IMAGE_REV="${MAYA_IMAGE_REV:-$(sed -n 's/^ARG MAYA_IMAGE_REV=//p' "$APP_DIR/$MAYA_DOCKERFILE" 2>/dev/null | head -1)}"
MAYA_TAG="${MAYA_REF:0:7}${MAYA_IMAGE_REV:+-r$MAYA_IMAGE_REV}"

on() { ssh -o BatchMode=yes -o ConnectTimeout=15 "stoke@$1" "${@:2}"; }

# render <values file in the chart dir> [helm args...]: helm template locally, with the helm CLI
# if installed, otherwise the alpine/helm image. --no-hooks keeps the helm test pod out.
render() {
  local values="$1"; shift
  if command -v helm >/dev/null; then
    helm template "$RELEASE" "$CHART" --namespace "$NAMESPACE" --no-hooks -f "$CHART/$values" "$@"
  else
    docker run --rm -v "$CHART:/chart:ro" alpine/helm:latest \
      template "$RELEASE" /chart --namespace "$NAMESPACE" --no-hooks -f "/chart/$values" "$@"
  fi
}

namespace_manifest() {
  cat <<EOF2
apiVersion: v1
kind: Namespace
metadata:
  name: $NAMESPACE
  labels:
    pod-security.kubernetes.io/enforce: restricted
EOF2
}

# The chart's templates carry no namespace, so every kubectl call passes -n.
apply_routes() {
  for u in "${PLATFORM[@]}"; do
    [ "$u" = "$HOME_UNIT" ] && continue
    { namespace_manifest; echo ---; render values-openstoke-standin.yaml; } | on "$u" "$KUBE apply -n $NAMESPACE -f -"
    echo "  $u: stand-in Service and route"
  done
}

# Flux guard: if a HelmRelease for this app exists on the home unit, Flux owns the namespace and a legacy
# apply would fight it (and be reverted). Refuse unless FORCE=1.
flux_guard() {
  [ -z "$FORCE" ] || return 0
  if on "$HOME_UNIT" "$KUBE -n $NAMESPACE get helmrelease.helm.toolkit.fluxcd.io $RELEASE >/dev/null 2>&1"; then
    cat >&2 <<EOF2
refusing: HelmRelease $RELEASE exists in namespace $NAMESPACE on $HOME_UNIT, so Flux owns this app.
A legacy apply would fight Flux. Use the Flux path instead (make release, then merge the stokeai-deploy PR),
or delete the HelmRelease first (kubectl -n $NAMESPACE delete helmrelease $RELEASE, or disable the app in
fleet.yaml), or override with FORCE=1.
EOF2
    return 1
  fi
}

# Preflight: Tailscale is up, the units we need are online, and ssh as `stoke` works non-interactively.
preflight() {
  local ts required u fp failed=0
  ts="$(command -v tailscale || true)"
  [ -n "$ts" ] || ts=/Applications/Tailscale.app/Contents/MacOS/Tailscale
  if ! [ -x "$ts" ]; then
    echo "preflight: tailscale CLI not found (install Tailscale, or put it on PATH)" >&2; return 1
  fi
  required="$(printf '%s\n' "$HOME_UNIT" "${PLATFORM[@]}" | sort -u | tr '\n' ' ')"

  echo "preflight: tailscale"
  "$ts" status --json 2>/dev/null \
    | python3 "$APP_DIR/deploy/tailnet.py" status --home "$HOME_UNIT" --required "$required" --fleet "${FLEET[*]}" \
    || return 1

  echo "preflight: ssh as stoke (Tailscale SSH)"
  for u in $required; do
    if on "$u" true 2>/dev/null; then
      echo "  $u ok"
    else
      failed=1
      fp="$("$ts" status --json 2>/dev/null | python3 "$APP_DIR/deploy/tailnet.py" fingerprint "$u" || true)"
      echo "  $u FAILED: if it's an unknown host key, check it matches ${fp:-the key Tailscale publishes} and accept once: ssh stoke@$u true" >&2
    fi
  done
  [ "$failed" = 0 ] || return 1
  echo "preflight: ok"
}

# A tag per commit; uncommitted changes are marked so an image never pretends to be a commit it is not.
compute_tag() {
  local t
  t="$(git -C "$APP_DIR" rev-parse --short HEAD)"
  [ -z "$(git -C "$APP_DIR" status --porcelain -- .)" ] || t="$t-dirty-$(date +%s)"
  echo "$t"
}

if [ "${1:-}" = "--home" ]; then   # the unit this script would use (no network); the reason goes to stderr
  echo "home unit: $HOME_UNIT ($HOME_WHY)" >&2
  echo "$HOME_UNIT"
  exit 0
fi

if [ "${1:-}" = "--tag" ]; then
  compute_tag
  exit 0
fi

if [ "${1:-}" = "--check" ]; then
  preflight
  exit $?
fi
echo "home unit: $HOME_UNIT ($HOME_WHY)"
if [ -z "${SKIP_PREFLIGHT:-}" ]; then
  preflight || { echo "deploy aborted: fix the preflight failures above (or SKIP_PREFLIGHT=1)" >&2; exit 1; }
fi

if [ "${1:-}" = "--routes" ]; then
  flux_guard || exit 1
  apply_routes
  exit 0
fi

# clean: delete the legacy-applied objects. Rendered manifests minus the PVCs (kept unless PURGE=1: they hold
# the voices, the cache and the job outputs), then the stand-ins on the other platform units.
if [ "${1:-}" = "--clean" ]; then
  flux_guard || exit 1
  echo "clean: delete the objects the legacy deploy applied in namespace $NAMESPACE on $HOME_UNIT"
  # shellcheck disable=SC2086
  render values-openstoke.yaml $HELM_EXTRA \
    | PURGE="$PURGE" python3 -c '
import os, re, sys
docs = re.split(r"(?m)^---\s*$", sys.stdin.read())
keep = [d for d in docs if d.strip() and (os.environ["PURGE"] or not re.search(r"(?m)^kind: PersistentVolumeClaim\s*$", d))]
print("\n---\n".join(keep))' \
    | on "$HOME_UNIT" "$KUBE delete -n $NAMESPACE --ignore-not-found -f -"
  if [ -n "$PURGE" ]; then
    echo "clean: PURGE=1, also deleting the Maya weights volume and every PVC of the release"
    on "$HOME_UNIT" "$KUBE -n $NAMESPACE delete pvc --ignore-not-found -l app.kubernetes.io/instance=$RELEASE"
  else
    echo "clean: the PVCs were kept (voices, out, cache, Maya weights); PURGE=1 deletes them too"
  fi
  for u in "${PLATFORM[@]}"; do
    [ "$u" = "$HOME_UNIT" ] && continue
    render values-openstoke-standin.yaml | on "$u" "$KUBE delete -n $NAMESPACE --ignore-not-found -f -"
    echo "  $u: stand-in Service and route removed"
  done
  exit 0
fi

flux_guard || exit 1

running_image() {
  on "$HOME_UNIT" "$KUBE -n $NAMESPACE get deployment $RELEASE -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null" || true
}

# prune_images: drop older images from docker and k3s on the home unit; keep $image and $previous (what ran before).
prune_images() {
  echo "6/6 prune older images (keep the new one and the one it replaced)"
  keep="${previous:-$image}"
  on "$HOME_UNIT" "docker images --format '{{.Repository}}:{{.Tag}}' mr-audio-smith | grep -vxF -e '$image' -e '$keep' | xargs -r docker rmi -f >/dev/null
    old=\$(docker run --rm --privileged --pid=host --network=host busybox nsenter -t 1 -m -u -n -i -- \
      k3s ctr -n k8s.io images ls -q | grep '^docker.io/library/mr-audio-smith:' | grep -vxF -e 'docker.io/library/$image' -e 'docker.io/library/$keep' || true)
    [ -z \"\$old\" ] || docker run --rm --privileged --pid=host --network=host busybox nsenter -t 1 -m -u -n -i -- \
      k3s ctr -n k8s.io images rm \$old >/dev/null
    echo \"  pruned: \$(echo \$old | wc -w | tr -d ' ') old image(s) from k3s\""
}

# copy_source: rsync the app directory to the home unit (build context for both Dockerfiles).
# Build output, local state and recordings stay home; the two directories of WAV files the build and the tests need
# (assets/stings, tests/fixtures/voices) are re-included before the blanket *.wav exclude.
copy_source() {
  rsync -a --delete \
    --include 'tests/fixtures/voices/*.wav' --include 'assets/stings/*.wav' \
    --exclude .venv --exclude node_modules --exclude /out --exclude .audio-smith --exclude /voices --exclude /models \
    --exclude dist --exclude /site --exclude coverage --exclude test-results --exclude playwright-report --exclude .git \
    --exclude '*.mp3' --exclude '*.wav' --exclude __pycache__ --exclude '.env*' --exclude .pytest_cache \
    --exclude .mypy_cache --exclude .ruff_cache --exclude htmlcov \
    "$APP_DIR/" "stoke@$HOME_UNIT:$SRC_DIR/"
}

# build_maya: build maya-tts:$MAYA_TAG from Dockerfile.maya2 on the home unit and import it into k3s, unless that
# tag is already imported there (the image is ~10 GB; it only changes with MAYA_REF or MAYA_IMAGE_REV).
# Needs the source copied by build_image.
build_maya() {
  [ -f "$APP_DIR/$MAYA_DOCKERFILE" ] && [ -z "${SKIP_MAYA:-}" ] || return 0
  [ -n "$MAYA_TAG" ] || { echo "maya: no MAYA_REF (ARG MAYA_REF in Dockerfile.maya2)" >&2; return 1; }
  local mimage="maya-tts:$MAYA_TAG"
  if on "$HOME_UNIT" "docker run --rm --privileged --pid=host --network=host busybox nsenter -t 1 -m -u -n -i -- \
       k3s ctr -n k8s.io images ls -q | grep -qxF docker.io/library/$mimage"; then
    echo "maya: $mimage already imported on $HOME_UNIT, skipping the build"
    return 0
  fi
  echo "maya: build $mimage (first time for this ref; this is big and takes a while) and import into k3s"
  on "$HOME_UNIT" "set -e
    docker build -q -f $SRC_DIR/$MAYA_DOCKERFILE --build-arg MAYA_REF=$MAYA_REF --build-arg MAYA_IMAGE_REV=$MAYA_IMAGE_REV -t $mimage $SRC_DIR >/dev/null
    docker save $mimage -o /tmp/maya-tts.tar
    docker run --rm --privileged --pid=host --network=host -v /tmp:/tmp busybox \
      nsenter -t 1 -m -u -n -i -- k3s ctr -n k8s.io images import /tmp/maya-tts.tar >/dev/null
    rm -f /tmp/maya-tts.tar"
}

# build_image: copy the source to the home unit, build there, import into k3s. Sets $tag and $image.
build_image() {
  tag="$(compute_tag)"
  image="mr-audio-smith:$tag"
  echo "image $image -> $HOME_UNIT"

  echo "1/6 copy the source to $HOME_UNIT"
  copy_source

  echo "2/6 build (native arm64, CPU only) and import into k3s"
  on "$HOME_UNIT" "set -e
    docker build -q -f $SRC_DIR/$APP_DOCKERFILE --build-arg VERSION=$tag -t $image $SRC_DIR >/dev/null
    docker save $image -o /tmp/mr-audio-smith.tar
    docker run --rm --privileged --pid=host --network=host -v /tmp:/tmp busybox \
      nsenter -t 1 -m -u -n -i -- k3s ctr -n k8s.io images import /tmp/mr-audio-smith.tar >/dev/null
    rm -f /tmp/mr-audio-smith.tar"
}

if [ "${1:-}" = "--maya" ]; then   # only the Maya TTS image (make image-maya)
  [ -f "$APP_DIR/$MAYA_DOCKERFILE" ] || { echo "no $MAYA_DOCKERFILE in $APP_DIR" >&2; exit 1; }
  SKIP_MAYA=
  copy_source
  build_maya
  echo "maya image ready on $HOME_UNIT: maya-tts:$MAYA_TAG"
  exit 0
fi

build_image
build_maya
if [ "${1:-}" = "--image" ]; then
  previous=$(running_image)
  prune_images
  echo "image ready on $HOME_UNIT: $image"
  [ -f "$APP_DIR/$MAYA_DOCKERFILE" ] && [ -z "${SKIP_MAYA:-}" ] && echo "maya image ready on $HOME_UNIT: maya-tts:$MAYA_TAG (the chart's maya2.image.tag in values-openstoke.yaml; no fleet pin needed)"
  echo "IMAGE_TAG=$tag"
  exit 0
fi

echo "3/6 apply on $HOME_UNIT"
# Remember what is running now: the prune below keeps it, so a rollback still has its image.
previous=$(running_image)
# shellcheck disable=SC2086
{ namespace_manifest; echo ---; render values-openstoke.yaml --set-string image.tag="$tag" --set-string maya2.image.tag="$MAYA_TAG" $HELM_EXTRA; } \
  | on "$HOME_UNIT" "$KUBE apply -n $NAMESPACE -f -"

echo "4/6 stand-ins and routes on the other platform clusters"
apply_routes

echo "5/6 wait for the rollout (the API does not wait for Maya; Maya downloads its model on first start, see: kubectl -n $NAMESPACE logs statefulset/$RELEASE-maya2)"
on "$HOME_UNIT" "$KUBE -n $NAMESPACE rollout status deployment/$RELEASE --timeout=15m"

prune_images

code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 "https://$HOST/healthz" || true)
echo "https://$HOST/healthz -> $code"
[ "$code" = 200 ]
