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
