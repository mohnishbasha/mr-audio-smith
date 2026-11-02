# mr-audio-smith developer commands. TypeScript targets run only when the package exists.
UV ?= uv
PY_EXTRAS ?= --extra dev --extra server --extra mcp --extra cloud
TS_PACKAGES := $(wildcard player/package-lock.json web/studio/package-lock.json integrations/pi/package-lock.json)

studio-build:
	cd web/studio && npm ci && npm run build

player-build:
	cd player && npm ci && npm run build

player-assets: player-build
	mkdir -p audio_smith/_assets/player && cp player/dist/audio-smith-player.js audio_smith/_assets/player/

package: studio-build player-assets
	$(UV) build

.PHONY: studio-build player-build player-assets package install lint format typecheck test test-int coverage smoke e2e check-versions build licenses docs clean record-llm

install:
	$(UV) sync $(PY_EXTRAS)

lint:
	$(UV) run ruff check .
	$(UV) run ruff format --check .
	$(UV) run python scripts/check_em_dash.py
	$(UV) run lint-imports
	@for p in $(dir $(TS_PACKAGES)); do (cd $$p && npm run --if-present lint) || exit 1; done

format:
	$(UV) run ruff format .
	$(UV) run ruff check --fix .

typecheck:
	$(UV) run mypy
	@for p in $(dir $(TS_PACKAGES)); do (cd $$p && npm run --if-present typecheck) || exit 1; done

test:
	$(UV) run pytest
	@for p in $(dir $(TS_PACKAGES)); do (cd $$p && npm run --if-present test) || exit 1; done

test-int:
	$(UV) run pytest -m integration -o addopts="-ra --strict-markers"

coverage:
	$(UV) run pytest --cov --cov-report=term --cov-report=json:coverage.json --cov-report=xml
	$(UV) run python scripts/check-coverage.py coverage.json .coverage-thresholds.toml
	@for p in $(dir $(TS_PACKAGES)); do (cd $$p && npm run --if-present coverage) || exit 1; done

smoke:
	bash tests/smoke/smoke.sh

e2e:
	cd tests/e2e && npm ci && npx playwright test && npx playwright test -c playwright.studio.config.ts

check-versions:
	./scripts/check-versions.sh

build:
	$(UV) build
	@for p in $(dir $(TS_PACKAGES)); do (cd $$p && npm run --if-present build) || exit 1; done

licenses:
	$(UV) run python scripts/check-licenses.py

docs:
	$(UV) run mkdocs build --strict

record-llm:
	$(UV) run python scripts/record-llm.py

clean:
	rm -rf dist build .pytest_cache .mypy_cache .ruff_cache htmlcov coverage.json coverage.xml out

# ---- Packaging (Sprint 9) ----
.PHONY: docker-cpu docker-cuda helm-lint
VERSION_TAG ?= dev

docker-cpu:
	docker build -f deploy/docker/Dockerfile.cpu --build-arg VERSION=$(VERSION_TAG) -t mr-audio-smith:cpu .

docker-cuda:
	docker build -f deploy/docker/Dockerfile.cuda --build-arg VERSION=$(VERSION_TAG) -t mr-audio-smith:cuda .

helm-lint:
	helm lint charts/mr-audio-smith
	helm template t charts/mr-audio-smith > /dev/null
	@for v in values-k3s-gpu.yaml values-ci.yaml values-openstoke.yaml values-openstoke-standin.yaml; do \
	  helm lint charts/mr-audio-smith -f charts/mr-audio-smith/$$v && \
	  helm template t charts/mr-audio-smith -f charts/mr-audio-smith/$$v > /dev/null || exit 1; \
	done

# ---- StokeAI DGX Spark platform (mr-audio-smith.openstoke.com, tailnet only) ----
# Same flow as the sibling apps. See docs/guide/stokeai.md.
#   make deploy          LEGACY direct apply into namespace mr-audio-smith (before Flux): build on the home unit, import into
#                        k3s, apply, stand-ins and routes, smoke test. Refused when a Flux HelmRelease owns the app (FORCE=1 overrides).
#   make deploy-routes   Re-apply only the stand-in Services and routes
#   make deploy-check    Preflight only: Tailscale up, all six units' status, ssh to the units deploy needs
#   make deploy-clean    Delete what `make deploy` applied; PVCs are kept unless PURGE=1
#   make image           Build on the home unit and import into k3s (preflight, rsync, build, prune); prints the tag
#   make image-maya      Build maya-tts:<ref>-r<rev> (Maya 2 server, big) on the home unit and import it; skips if present
#   make helm-package    Package the chart -> dist/<chart>-<version>.tgz
#   make helm-push       Push the chart to $(CHART_REPO) (refuses if the version exists; helm registry login ghcr.io first)
#   make release         image + helm-push (if unpublished) + pin both in $(DEPLOY_REPO)/fleet.yaml on a branch, render, commit
#                        (ENABLE=1 also sets enabled: true; no push, no PR: prints the gh pr create command)
.PHONY: deploy deploy-routes deploy-check deploy-clean image image-maya helm-package helm-push release
RELEASE      ?= mr-audio-smith
CHART        ?= charts/mr-audio-smith
HELM         ?= helm
NAMESPACE    ?= mr-audio-smith
CHART_REPO   ?= oci://ghcr.io/mohnishbasha/charts
CHART_NAME    = $(notdir $(CHART))
CHART_VERSION = $(shell sed -n 's/^version: *//p' $(CHART)/Chart.yaml | tr -d '"' | head -1)
CHART_PKG     = dist/$(CHART_NAME)-$(CHART_VERSION).tgz
DEPLOY_REPO  ?= ../../stokeai-deploy
ENABLE       ?=
FORCE        ?=
PURGE        ?=
RELEASE_ENV   = HELM="$(HELM)" CHART_REPO="$(CHART_REPO)" DEPLOY_REPO="$(DEPLOY_REPO)" ENABLE="$(ENABLE)"
DEPLOY_ENV    = FORCE="$(FORCE)" PURGE="$(PURGE)"

deploy:
	$(DEPLOY_ENV) deploy/deploy.sh

deploy-routes:
	$(DEPLOY_ENV) deploy/deploy.sh --routes

deploy-check:
	deploy/deploy.sh --check

deploy-clean:
	$(DEPLOY_ENV) deploy/deploy.sh --clean

# Preflight, rsync, build on the home unit, import into k3s, prune. Prints IMAGE_TAG=<tag>.
image:
	deploy/deploy.sh --image

# The Maya 2 server image (Dockerfile.maya2; ~10 GB). `make image` builds it too when it is not imported yet.
image-maya:
	deploy/deploy.sh --maya

# Charts are OCI artifacts; a published version is never republished: bump `version` in Chart.yaml first.
# One-time before pushing:  helm registry login ghcr.io -u <github-user>   (password: a gh token with write:packages)
helm-package:
	@mkdir -p dist
	$(HELM) package $(CHART) --destination dist

helm-push: helm-package
	@rc=0; $(RELEASE_ENV) deploy/release.sh published || rc=$$?; \
	  if [ $$rc = 0 ]; then echo "refusing: $(CHART_NAME) $(CHART_VERSION) is already in $(CHART_REPO). Bump version in $(CHART)/Chart.yaml."; exit 1; \
	  elif [ $$rc != 1 ]; then exit $$rc; fi
	$(HELM) push $(CHART_PKG) $(CHART_REPO)

# fleet.yaml only takes a clean git sha, so a dirty tree is refused: commit first.
release:
	@case "$$(deploy/deploy.sh --tag)" in *dirty*) echo "release: uncommitted changes under $(CURDIR); commit first (fleet.yaml takes only a clean git sha)"; exit 1;; esac
	$(MAKE) image
	@rc=0; $(RELEASE_ENV) deploy/release.sh published || rc=$$?; \
	  if [ $$rc = 1 ]; then $(MAKE) helm-push; \
	  elif [ $$rc = 0 ]; then echo "chart $(CHART_NAME) $(CHART_VERSION) already published, not pushing"; \
	  else exit $$rc; fi
	IMAGE_HOME="$$(deploy/deploy.sh --home 2>/dev/null)" $(RELEASE_ENV) deploy/release.sh pin "$$(deploy/deploy.sh --tag)"
