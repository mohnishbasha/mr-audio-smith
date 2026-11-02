# Deploy on StokeAI

mr-audio-smith runs on the StokeAI DGX Spark platform at `https://mr-audio-smith.openstoke.com` (tailnet only). It
follows the same pattern as the other SnackOnAI apps and is independent of them: its own namespace
(`mr-audio-smith`), its own chart, its own secret and its own Maya 2 voice server.

| Piece | Where it runs |
|---|---|
| API (`mr-audio-smith serve`), CPU only | Deployment `mr-audio-smith` on the home unit `spark-bundle2-1`, strategy Recreate, PVCs on `local-path` |
| Maya 2 voice server (GPU) | StatefulSet `mr-audio-smith-maya2` on the same unit. GPU through CDI (`runtimeClassName: nvidia`, `NVIDIA_VISIBLE_DEVICES=all`), never an `nvidia.com/gpu` request. Port 8080, ClusterIP only, a NetworkPolicy lets only the API pod in |
| Script writing LLM | The platform's shared SGLang model `qwen38-27b` (no Ollama, no vLLM in this app) |
| Route | HTTPRoute on Gateway `stoke-gw` (namespace `gateway`); stand-in Service and route on `spark-bundle1-1-7229` and `spark-bundle3-1-763e` |
| Server token | Bao `secret/stoke/mr-audio-smith`, property `server_token`, through an ExternalSecret (ClusterSecretStore `openbao`) |

The namespace enforces PodSecurity `restricted`: every pod runs as non-root with the RuntimeDefault seccomp
profile, no privilege escalation and all capabilities dropped. Because of that the root init container that fixes
volume permissions is off on this platform.

## Prerequisites

1. **Tailscale** is up on your Mac and Tailscale SSH works as `stoke@<unit>`. Check with `make deploy-check`
   (it prints the status of all six units and tries `ssh stoke@<unit> true` on the ones the deploy needs).
   The first connection to a unit may ask you to accept its host key once: `ssh stoke@spark-bundle2-1 true`.
2. **Docker, helm, kubectl, rsync** locally (helm falls back to the `alpine/helm` image if missing).
3. **The server token in Bao.** The API binds `0.0.0.0`, so it refuses to start without one:

    ```bash
    bao kv put secret/stoke/mr-audio-smith server_token=$(openssl rand -hex 32)
    ```

4. **For the Flux path only:** log in to GitHub Container Registry so the chart can be pushed:

    ```bash
    gh auth refresh -s write:packages
    gh auth token | helm registry login ghcr.io -u <github-user> --password-stdin
    ```

   and a checkout of `stokeai-deploy` at `../../stokeai-deploy` (override with `DEPLOY_REPO=`), with PyYAML
   installed for its `render/render.py`.

The home unit is `spark-bundle2-1`. `deploy.sh` takes it from `HOME_UNIT`, else from the `home:` on the
`mr-audio-smith` line of `stokeai-deploy/fleet.yaml`, else the built-in default. `deploy/deploy.sh --home` prints it.

## Path 1: Flux (preferred)

Flux owns the app. You build the image on the home unit, publish the chart and open a pull request in
`stokeai-deploy`.

1. Commit your changes. `make release` refuses a dirty tree because `fleet.yaml` only takes a clean git sha.
2. If you changed anything under `charts/mr-audio-smith`, bump the chart `version` in `Chart.yaml` (a plain
   `x.y.z`, starting at `0.1.0`). A published chart version is never republished. `appVersion` tracks
   `pyproject.toml` and is set by `scripts/bump-version.sh`.
3. Run:

    ```bash
    make release            # add ENABLE=1 to also set enabled: true on the fleet line
    ```

   This preflights the tailnet, copies the source to the home unit, builds `mr-audio-smith:<git sha>` there from
   `deploy/docker/Dockerfile.cpu` and imports it into k3s. It also builds `maya-tts:<ref>-r<rev>` from
   `deploy/docker/Dockerfile.maya2` the first time (about 10 GB, skipped when already imported; `SKIP_MAYA=1`
   skips it). Then it pushes the chart to `oci://ghcr.io/mohnishbasha/charts` if that version is not published
   yet, and commits the chart version and image tag into `stokeai-deploy/fleet.yaml` on a branch.
4. Push that branch and open the PR (the command is printed). Flux rolls it out after the merge.

The images only exist on the home unit (`pullPolicy: Never`), so the `home:` on the fleet line must match the unit
the image was built on; `release.sh pin` refuses otherwise.

Individual steps: `make image`, `make image-maya`, `make helm-package`, `make helm-push`.

## Path 2: legacy direct apply

For work before Flux owns the app. Same namespace, no Flux.

```bash
make deploy         # build, import, helm template | kubectl apply on the home unit, stand-ins, routes, rollout, smoke test
make deploy-routes  # only the stand-in Services and routes on the other platform units
make deploy-clean   # delete what make deploy applied (PVCs are kept; PURGE=1 deletes them too)
```

The smoke test waits for `rollout status deployment/mr-audio-smith` and expects
`https://mr-audio-smith.openstoke.com/healthz` to answer 200. Maya 2 downloads about 5 GB into the `models` volume
on its first start and the API does not wait for it; follow it with
`kubectl -n mr-audio-smith logs -f statefulset/mr-audio-smith-maya2`.

**Flux guard.** If `kubectl -n mr-audio-smith get helmrelease mr-audio-smith` finds a HelmRelease on the home unit,
Flux owns the app and `deploy`, `deploy-routes` and `deploy-clean` refuse to run, because a direct apply would fight
Flux and be reverted. Use the Flux path, or delete the HelmRelease first
(`kubectl -n mr-audio-smith delete helmrelease mr-audio-smith`, or disable the app in `fleet.yaml`), or set
`FORCE=1` if you really mean it.

## Use it

```bash
export TOKEN=$(bao kv get -field=server_token secret/stoke/mr-audio-smith)
curl https://mr-audio-smith.openstoke.com/healthz
curl -H "Authorization: Bearer $TOKEN" https://mr-audio-smith.openstoke.com/v1/jobs
mr-audio-smith run https://example.com/post --server https://mr-audio-smith.openstoke.com --token "$TOKEN"
```

### Register a voice

Voices are stored on the `voices` volume (directory mode 0700) and need a consent record, so register them inside
the pod. Copy the clip in, then run `voice add` (see [Voices and consent](voices-and-consent.md) for the flags):

```bash
kubectl -n mr-audio-smith cp ./my-clip.wav deploy/mr-audio-smith:/tmp/my-clip.wav
kubectl -n mr-audio-smith exec -it deploy/mr-audio-smith -- mr-audio-smith voice add --help
kubectl -n mr-audio-smith exec -it deploy/mr-audio-smith -- mr-audio-smith voice add <id> --clip /tmp/my-clip.wav ...
```

`/tmp` is an emptyDir, so the clip disappears when the pod restarts; the registered voice stays on the `voices`
volume. Run `kubectl -n mr-audio-smith exec deploy/mr-audio-smith -- mr-audio-smith voice list` to check.

## Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| `make deploy-check` fails on a unit | Tailscale is down, or the unit is offline, or the host key is not accepted yet (`ssh stoke@<unit> true`). The error prints the key fingerprint Tailscale publishes. |
| `deploy` refuses: "HelmRelease ... exists" | Flux owns the app. See the Flux guard above. |
| `ErrImageNeverPull` on the API or Maya pod | The image is not imported on the home unit. `make image` / `make image-maya`, and check `HOME_UNIT` matches the fleet `home:`. |
| Pod `Pending` with `Insufficient nvidia.com/gpu` | Something requests the GPU as a resource. The StokeAI values use `maya2.gpu.mode: cdi`, which never does; check you rendered with `values-openstoke.yaml`. |
| Pod rejected by PodSecurity | A root container sneaked in. `initPermissions.enabled` must be `false` here and every container needs `runAsNonRoot`, `allowPrivilegeEscalation: false` and `drop: [ALL]`. |
| API starts but `ExternalSecret` is not ready, pod `CreateContainerConfigError` | The Bao key is missing: run the `bao kv put` above. `kubectl -n mr-audio-smith describe externalsecret mr-audio-smith`. |
| `/healthz` is 200 but narration fails with a backend error | Maya 2 is still downloading or loading. `kubectl -n mr-audio-smith logs -f statefulset/mr-audio-smith-maya2`; it is ready when `/health` answers 200. |
| Script writing fails | The shared SGLang service `qwen38-27b-api.serving.svc.cluster.local:8000` is not reachable from the namespace or the model is loading. |
| `doctor` warns the voices directory is broader than 0700 | `local-path` mounts the volume root world-writable and the app cannot chmod a directory it does not own. Voices created by the app are 0700; the warning is about the mount root only. |
| `https://mr-audio-smith.openstoke.com` does not answer from a client | You must be on the tailnet. Check the stand-ins with `make deploy-routes` (legacy) or the Flux status of the app on the other platform units. |
