# Deployment

There are three tiers. All of them run the same application; they differ in how you start Maya 2, the script
LLM, and the REST API.

| Tier | Use it for | Needs |
|---|---|---|
| 1. Local binary | One person, one machine | Python 3.12, ffmpeg, optional GPU |
| 2. Docker Compose | A workstation or a single server | Docker; NVIDIA Container Toolkit for the GPU stack |
| 3. Helm | A cluster | Kubernetes; NVIDIA device plugin for Maya 2 |

## Tier 1: local binary

```bash
uv tool install "mr-audio-smith[server,kokoro]"     # or: pipx install "mr-audio-smith[server,kokoro]"
mr-audio-smith doctor
```

Maya 2 is optional and runs as its own server (needs a Linux NVIDIA GPU). Start it as its README describes, then
`mr-audio-smith doctor` verifies it at `http://127.0.0.1:8080/v1`.

## Tier 2: Docker Compose

Images are built from `deploy/docker/`:

| File | Image | Notes |
|---|---|---|
| `Dockerfile.cpu` | `mr-audio-smith:<version>` | Python 3.12 slim, ffmpeg, espeak-ng, Kokoro on CPU torch. Default backend `kokoro`. |
| `Dockerfile.cuda` | `mr-audio-smith:<version>-cuda` | NVIDIA CUDA 12.8 runtime, CUDA torch. A CUDA 13 build arg exists for the DGX Spark GB10. |
| `Dockerfile.maya2` | `maya2-server:79142d8` | Upstream Maya 2 server at a pinned commit, port 8080, CUDA 13. |

Both app images run as uid 10001, write only under `/var/lib/audio-smith` and `/tmp`, so they work with a
read-only root filesystem. They are not distroless because the pipeline needs ffmpeg and espeak-ng.

**GPU host** (Ollama, Maya 2, API; weights are pre-pulled by the `ollama-pull` and `maya2-pull` services):

```bash
export AUDIO_SMITH_SERVER_TOKEN=$(openssl rand -hex 32)
docker compose -f deploy/docker-compose.local.yml up --build
curl -H "Authorization: Bearer $AUDIO_SMITH_SERVER_TOKEN" http://127.0.0.1:7340/v1/jobs
```

**Laptop, no GPU** (the `cpu` profile: Kokoro, a small Ollama model, no Maya 2). Naming the service starts only it
and its dependencies:

```bash
docker compose -f deploy/docker-compose.local.yml --profile cpu up --build audio-smith-cpu
```

**Production**: `deploy/docker-compose.prod.yml` pins images by digest (replace the placeholder digests with the
ones you verified), sets CPU and memory limits, read-only root filesystems with a tmpfs `/tmp`, json-file log
rotation, and restart policies. Ollama and Maya 2 sit on an internal network with no published ports. Only Caddy
publishes ports (80 and 443) and obtains a TLS certificate automatically (`deploy/caddy/Caddyfile`).

```bash
AUDIO_SMITH_DOMAIN=narrate.example.com ACME_EMAIL=ops@example.com \
AUDIO_SMITH_SERVER_TOKEN=$(openssl rand -hex 32) \
docker compose -f deploy/docker-compose.prod.yml up -d
```

The internal network has no route to the internet, so populate the model volumes first with
`docker compose -f deploy/docker-compose.local.yml up ollama-pull maya2-pull` (both files share the project name
`audio-smith`).

## Tier 3: Helm

The chart is in `charts/mr-audio-smith` and is published to `oci://ghcr.io/serverless-ventures/charts`. See the
chart README for every value.

**k3s with GPUs (and Cilium).** Install the NVIDIA container toolkit and device plugin on the GPU nodes, then:

```bash
helm install audio-smith charts/mr-audio-smith -n audio-smith --create-namespace \
  -f charts/mr-audio-smith/values-k3s-gpu.yaml \
  --set ingress.hosts[0].host=narrate.example.com --set ingress.tls[0].hosts[0]=narrate.example.com
kubectl rollout status -n audio-smith statefulset/audio-smith-mr-audio-smith-maya2
```

The first Maya 2 start downloads about 5 GB into the 50Gi `models` volume (an init container, with an optional
checksum file in `maya2.weights.sha256sums`). On NVIDIA Grace (arm64) nodes, the values file shows how to pin Maya 2
to arm64 and swap Ollama for `nvcr.io/nvidia/vllm-openai`.

**kind, CPU profile** (mock backend, no GPU, used by CI):

```bash
docker build -f deploy/docker/Dockerfile.cpu -t mr-audio-smith:ci .
kind create cluster && kind load docker-image mr-audio-smith:ci
helm install audio-smith charts/mr-audio-smith -f charts/mr-audio-smith/values-ci.yaml
```

## Security notes

- The Maya 2 server has **no authentication**. Never publish port 8080 or bind it to a public interface. Compose
  keeps it on a private network; the chart exposes it as a ClusterIP Service and a NetworkPolicy admits only the
  API pods. Ollama and vLLM have the same rule.
- `serve` refuses to bind a non-loopback address without `AUDIO_SMITH_SERVER_TOKEN`. Every compose file and the
  chart require one (the chart generates a random token if you give none).
- Containers run as a non-root user with all capabilities dropped, no privilege escalation, and a read-only root
  filesystem. The chart's one root step is a short init container that makes the `voices` directory 0700; disable it
  with `initPermissions.enabled=false` on clusters enforcing the restricted Pod Security Standard and provision the
  volume yourself.
- Cloned-voice clips and consent records live on the `voices` volume. Treat that volume as secret.
- Images and the chart are signed with keyless cosign and carry provenance and SBOM attestations:

```bash
cosign verify ghcr.io/serverless-ventures/mr-audio-smith:<version> \
  --certificate-identity-regexp 'https://github.com/mohnishbasha/mr-audio-smith/.*' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
```

## Publishing (maintainers)

The release workflow builds, pushes, and signs images and the chart only when the repository variable
`IMAGES_PUBLISH` is `true`. The owner must first allow GHCR package writes for the organization
`serverless-ventures` (grant the repository write access on each package). Until then a tag still builds wheels,
SBOMs, and the GitHub Release.

## Verified

Checked on 2026-11-02 on an arm64 Mac with Docker Desktop and Helm:

- `docker build -f deploy/docker/Dockerfile.cpu -t mr-audio-smith:cpu .` succeeds: about 0.46 GB compressed and
  1.4 GB unpacked (static ffmpeg instead of Debian's package, CPU torch, stripped shared libraries, and no `qa`
  extra in the CPU image; speaker similarity QA matters most for cloned voices on the CUDA image).
- Inside the image, with `--read-only` and tmpfs mounts, `run tests/fixtures/pages/letter-calm.html --llm fake
  --backend mock` produces the MP3 (-16.4 LUFS), captions, embed, and manifest.
- `docker run --rm -e AUDIO_SMITH_LLM=fake mr-audio-smith:cpu doctor --json` reports `ok: true`. Without a
  reachable Ollama, the required `llm` check fails by design; Maya 2 is reported unreachable (optional).
- The container serves `/healthz` and reports healthy with `--read-only` and a tmpfs `/tmp`.
- `helm lint` and `helm template` pass for the default values, `values-k3s-gpu.yaml`, and `values-ci.yaml`.
- `docker compose config` passes for the local file (default and `cpu` profile) and the prod file.
- Not verified locally: the CUDA and Maya 2 images (syntax checked with `docker build --check` only), the GPU
  compose stack, a Helm install on a GPU cluster, `ct install` in kind (runs in CI), and the release workflow's
  signing (needs GHCR access).
