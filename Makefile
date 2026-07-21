WP07_ARTIFACT_DIR ?= artifacts/wp07-candidate
WP07_IMAGE_PREFIX ?= journey-next-candidate
WP07_SHA := $(shell git rev-parse --verify HEAD 2>/dev/null || printf no-head)
WP07_API_IMAGE := $(WP07_IMAGE_PREFIX)-api:$(WP07_SHA)
WP07_WEB_IMAGE := $(WP07_IMAGE_PREFIX)-web:$(WP07_SHA)
WP07_WORKER_IMAGE := $(WP07_IMAGE_PREFIX)-worker:$(WP07_SHA)
WP07_GHCR_PREFIX ?= ghcr.io/muchenai2024-creator/muchen-journey-vnext
WP07_API_GHCR_IMAGE := $(WP07_GHCR_PREFIX)-api:$(WP07_SHA)
WP07_WEB_GHCR_IMAGE := $(WP07_GHCR_PREFIX)-web:$(WP07_SHA)
WP07_WORKER_GHCR_IMAGE := $(WP07_GHCR_PREFIX)-worker:$(WP07_SHA)
WP07_GITLEAKS_IMAGE := ghcr.io/gitleaks/gitleaks@sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f
WP07_SYFT_IMAGE := anchore/syft@sha256:b4f1df79f97b817682d8b5ff941eb6bfe74f6172553a5e312c75bbc2eabc405c
WP07_PYTHON_IMAGE := python:3.14.6-slim@sha256:cea0e6040540fb2b965b6e7fb5ffa00871e632eef63719f0ea54bca189ce14a6
WP08_LOCAL_DB_PORT ?= 35432
WP08_LOCAL_API_PORT ?= 38000

.PHONY: bootstrap up down migrate seed api-test migration-check migration-static-check fixture-manifest web-install web-static web-check openapi-check isolation-check legacy-reference-scan traceability-check secret-scan dependency-audit ci-fast ci-main candidate-preflight candidate-images candidate-task-versions candidate-sboms candidate-package candidate-registry-check candidate-registry-push http-negative-check verify wp06-backup wp06-drill wp06-alert-sim release-gate release-gate-check wp08-cold-preflight wp08-evidence-init wp08-evidence-check wp08-git-check browser-preflight browser-smoke

bootstrap:
	docker compose build api worker
	cd apps/web && npm ci

up:
	docker compose up --build

down:
	docker compose down

migrate:
	docker compose run --rm api alembic upgrade head

seed:
	docker compose run --rm api python -m journey_api.seed

api-test:
	docker compose up --wait db-test
	docker compose build api
	docker compose exec -T db-test dropdb -U journey_next --if-exists --force journey_next_test
	docker compose exec -T db-test createdb -U journey_next journey_next_test
	docker compose run --rm --no-deps -e DATABASE_URL=postgresql+psycopg://journey_next:journey_next_test@db-test:5432/journey_next_test api sh -ec 'alembic upgrade head; python -m journey_api.seed; pytest -q'

migration-check:
	MJ_DB_PORT=$${MJ_DB_PORT:-$(WP08_LOCAL_DB_PORT)} python3 scripts/wp06_ops.py migration-check

migration-static-check:
	python3 scripts/wp08_readiness.py migration-static

fixture-manifest:
	python3 scripts/wp08_readiness.py fixture-manifest --output artifacts/wp08/fixture-manifest.json

web-install:
	cd apps/web && npm ci

web-static:
	cd apps/web && npm run lint && npm run typecheck

web-check: web-static
	cd apps/web && npm run build

openapi-check:
	docker compose run --rm --no-deps api python -c 'import json; from pathlib import Path; from journey_api.main import app; expected=json.loads(Path("contracts/openapi.json").read_text()); assert app.openapi() == expected, "runtime OpenAPI differs from contracts/openapi.json"'

isolation-check:
	./scripts/check_isolation.sh

legacy-reference-scan: isolation-check

traceability-check:
	python3 scripts/wp07_candidate.py check

secret-scan:
	docker run --rm -v "$(CURDIR):/repo:ro" $(WP07_GITLEAKS_IMAGE) dir /repo --config /repo/.gitleaks.toml --redact --no-banner --exit-code 1

dependency-audit:
	cd apps/web && npm audit --audit-level=low
	docker run --rm -v "$(CURDIR):/src:ro" -w /tmp $(WP07_PYTHON_IMAGE) sh -ec 'python -m pip install --disable-pip-version-check --no-cache-dir pip-audit==2.10.1 >/dev/null && python -m pip_audit --progress-spinner=off -r /src/requirements.lock'

ci-fast:
	$(MAKE) web-install
	$(MAKE) traceability-check legacy-reference-scan secret-scan dependency-audit
	$(MAKE) api-test openapi-check web-static

ci-main:
	$(MAKE) ci-fast
	$(MAKE) migration-check web-check http-negative-check release-gate-check

candidate-preflight:
	python3 scripts/wp07_candidate.py preflight

candidate-images:
	docker build --pull --build-arg VCS_REF=$(WP07_SHA) -t $(WP07_API_IMAGE) -f apps/api/Dockerfile .
	docker build --pull --build-arg VCS_REF=$(WP07_SHA) -t $(WP07_WORKER_IMAGE) -f apps/worker/Dockerfile .
	docker build --pull --build-arg VCS_REF=$(WP07_SHA) -t $(WP07_WEB_IMAGE) -f apps/web/Dockerfile apps/web

candidate-task-versions:
	mkdir -p $(WP07_ARTIFACT_DIR)
	docker compose up --wait db-test
	docker compose exec -T db-test dropdb -U journey_next --if-exists --force journey_next_test
	docker compose exec -T db-test createdb -U journey_next journey_next_test
	docker compose build api
	docker compose run --rm --no-deps -e DATABASE_URL=postgresql+psycopg://journey_next:journey_next_test@db-test:5432/journey_next_test api sh -ec 'alembic upgrade head; python -m journey_api.seed'
	docker compose run -T --rm --no-deps -e DATABASE_URL=postgresql+psycopg://journey_next:journey_next_test@db-test:5432/journey_next_test api python scripts/wp07_candidate.py task-versions --output /tmp/task-versions.json > $(WP07_ARTIFACT_DIR)/task-versions.json

candidate-sboms:
	mkdir -p $(WP07_ARTIFACT_DIR)
	docker run --rm -v /var/run/docker.sock:/var/run/docker.sock -v "$(CURDIR)/$(WP07_ARTIFACT_DIR):/out" $(WP07_SYFT_IMAGE) $(WP07_API_IMAGE) -o spdx-json=/out/api.spdx.json
	docker run --rm -v /var/run/docker.sock:/var/run/docker.sock -v "$(CURDIR)/$(WP07_ARTIFACT_DIR):/out" $(WP07_SYFT_IMAGE) $(WP07_WEB_IMAGE) -o spdx-json=/out/web.spdx.json
	docker run --rm -v /var/run/docker.sock:/var/run/docker.sock -v "$(CURDIR)/$(WP07_ARTIFACT_DIR):/out" $(WP07_SYFT_IMAGE) $(WP07_WORKER_IMAGE) -o spdx-json=/out/worker.spdx.json

candidate-package:
	$(MAKE) candidate-preflight
	$(MAKE) candidate-images
	$(MAKE) candidate-task-versions
	$(MAKE) candidate-sboms
	python3 scripts/wp07_candidate.py generate --output $(WP07_ARTIFACT_DIR)/release-manifest.json --task-versions $(WP07_ARTIFACT_DIR)/task-versions.json --image api=$(WP07_API_IMAGE) --image web=$(WP07_WEB_IMAGE) --image worker=$(WP07_WORKER_IMAGE) --sbom api=$(WP07_ARTIFACT_DIR)/api.spdx.json --sbom web=$(WP07_ARTIFACT_DIR)/web.spdx.json --sbom worker=$(WP07_ARTIFACT_DIR)/worker.spdx.json
	python3 scripts/wp07_candidate.py verify $(WP07_ARTIFACT_DIR)/release-manifest.json

candidate-registry-check:
	python3 scripts/wp07_candidate.py registry-check --commit $(WP07_SHA) --registry-image api=$(WP07_API_GHCR_IMAGE) --registry-image web=$(WP07_WEB_GHCR_IMAGE) --registry-image worker=$(WP07_WORKER_GHCR_IMAGE)

candidate-registry-push: candidate-registry-check
	@test "$(GITHUB_ACTIONS)" = "true"
	@test "$(GITHUB_EVENT_NAME)" = "push"
	@test "$(GITHUB_REF)" = "refs/heads/main"
	@test "$(WP07_REGISTRY_PUSH)" = "1"
	docker tag $(WP07_API_IMAGE) $(WP07_API_GHCR_IMAGE)
	docker tag $(WP07_WEB_IMAGE) $(WP07_WEB_GHCR_IMAGE)
	docker tag $(WP07_WORKER_IMAGE) $(WP07_WORKER_GHCR_IMAGE)
	docker push $(WP07_API_GHCR_IMAGE)
	docker push $(WP07_WEB_GHCR_IMAGE)
	docker push $(WP07_WORKER_GHCR_IMAGE)
	python3 scripts/wp07_candidate.py registry --manifest $(WP07_ARTIFACT_DIR)/release-manifest.json --registry-image api=$(WP07_API_GHCR_IMAGE) --registry-image web=$(WP07_WEB_GHCR_IMAGE) --registry-image worker=$(WP07_WORKER_GHCR_IMAGE)

http-negative-check:
	MJ_DB_PORT=$${MJ_DB_PORT:-$(WP08_LOCAL_DB_PORT)} MJ_API_PORT=$${MJ_API_PORT:-$(WP08_LOCAL_API_PORT)} docker compose up --build -d --wait db api
	MJ_API_PORT=$${MJ_API_PORT:-$(WP08_LOCAL_API_PORT)} python3 scripts/wp06_ops.py http-negative

verify: api-test migration-check web-check isolation-check http-negative-check release-gate-check

wp06-backup:
	python3 scripts/wp06_ops.py backup

wp06-drill:
	python3 scripts/wp06_ops.py drill --latest

wp06-alert-sim:
	python3 scripts/wp06_ops.py alert-sim

release-gate:
	python3 scripts/wp06_ops.py release-gate config/wp06_release_gate.local.json

release-gate-check:
	python3 scripts/wp06_ops.py release-gate config/wp06_release_gate.local.json --expect-no-go

wp08-cold-preflight:
	python3 scripts/wp08_readiness.py cold-preflight

wp08-evidence-init:
	python3 scripts/wp08_readiness.py evidence-init

wp08-evidence-check:
	python3 scripts/wp08_readiness.py evidence-check

wp08-git-check:
	python3 scripts/wp08_readiness.py git-check

browser-preflight:
	python3 scripts/wp08_readiness.py browser-preflight

browser-smoke: browser-preflight
	sh scripts/wp08_browser_smoke.sh
