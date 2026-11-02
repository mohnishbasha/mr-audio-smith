# mr-audio-smith Helm chart

Deploys the mr-audio-smith REST API with optional Maya 2 (TTS), Ollama or vLLM (script LLM), a Secret for the
API token, PVCs, Ingress, NetworkPolicy and an HPA.

| Workload | Kind | Notes |
|---|---|---|
| `audio-smith` | Deployment | non-root (10001), read-only rootfs, PVCs `cache`, `out`, `voices` (0700) |
| `maya2` | StatefulSet | `nvidia.com/gpu: 1`, PVC `models` 50Gi, init container pre-downloads and checksums weights, readiness on `/health` port 8080 |
| `ollama` | StatefulSet + pull Job | optional, PVC 100Gi, Job pulls `ollama.model` after install |
| `vllm` | Deployment | optional OpenAI-compatible endpoint instead of Ollama |

Maya 2, Ollama and vLLM have no authentication. They are ClusterIP only, and the NetworkPolicy lets only the
`audio-smith` pods (and the model-pull Job) reach them. Never add an Ingress for them.

## Install

```bash
# GPU cluster (k3s + Cilium): see values-k3s-gpu.yaml for the prerequisites
helm install audio-smith charts/mr-audio-smith -n audio-smith --create-namespace -f charts/mr-audio-smith/values-k3s-gpu.yaml

# From the registry (after a release)
helm install audio-smith oci://ghcr.io/serverless-ventures/charts/mr-audio-smith --version <version> -n audio-smith --create-namespace

# CPU smoke test in kind (mock backend, no GPU)
helm install audio-smith charts/mr-audio-smith -f charts/mr-audio-smith/values-ci.yaml --set image.tag=<tag>
```

Read the generated API token with the command printed in the install notes.

## Key values

| Value | Default | Meaning |
|---|---|---|
| `image.tag` / `image.variant` | appVersion / `""` | `variant: "-cuda"` selects the CUDA image |
| `maya2.enabled` / `maya2.externalUrl` | `true` / `""` | run Maya 2 here, or point at an existing server |
| `maya2.weights.revision` / `.sha256sums` | `main` / `""` | pin a Hugging Face revision; optional checksum file verified by the init container |
| `ollama.enabled` / `ollama.model` | `true` / `qwen3:14b` | Ollama StatefulSet and the model the pull Job fetches |
| `vllm.enabled` | `false` | replaces Ollama (`nvcr.io/nvidia/vllm-openai`) |
| `auth.token` / `auth.existingSecret` | generated | `AUDIO_SMITH_SERVER_TOKEN` |
| `persistence.*` | enabled | `cache` becomes ReadWriteMany when more than one replica can run |
| `autoscaling.*` | off | CPU HPA; `queueDepth` adds a Pods metric (needs a custom-metrics adapter) |
| `networkPolicy.enabled` | `true` | restrict Maya 2 and the LLM servers to the API pods |
| `ingress.*` | off | TLS, `proxy-read-timeout: 600`, `proxy-body-size: 10m`, optional basic auth |

With more than one API replica, `out` and `voices` must also be ReadWriteMany.

## Checks

```bash
make helm-lint        # helm lint + helm template for default, values-k3s-gpu.yaml, values-ci.yaml
```

CI (`.github/workflows/helm.yml`) also runs `ct install` in kind with `values-ci.yaml`.
