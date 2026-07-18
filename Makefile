.PHONY: frontend-build docker-build-atom-openmm docker-build-gcncmcmd docker-build-orchestrator docker-push-atom-openmm docker-push-gcncmcmd docker-push-orchestrator release-cli setup-hooks local-build-images local-build-sif-or-sandbox local-install-cli local-smoke

setup-hooks:
	git config core.hooksPath .githooks
	chmod +x .githooks/pre-commit .githooks/pre-push

ORG ?= your-org
ATOM_OPENMM_BASE_IMAGE ?= ghcr.io/$(ORG)/relaymd-worker-atom-openmm-base:latest
GCNCMC_BASE_IMAGE ?= ghcr.io/$(ORG)/relaymd-worker-gcncmcmd-base:latest
ATOM_OPENMM_IMAGE ?= ghcr.io/$(ORG)/relaymd-worker-atom-openmm:latest
GCNCMC_IMAGE ?= ghcr.io/$(ORG)/relaymd-worker-gcncmcmd:latest
ORCHESTRATOR_IMAGE ?= ghcr.io/$(ORG)/relaymd-orchestrator:latest
BUILD ?= 0

frontend-build:
	cd frontend && npm --cache ./.npm install
	cd frontend && npm --cache ./.npm run build

docker-build-atom-openmm:
	docker build -t $(ATOM_OPENMM_BASE_IMAGE) -f Dockerfile.worker-atom-openmm-base .
	docker build --build-arg BASE_IMAGE=$(ATOM_OPENMM_BASE_IMAGE) -t $(ATOM_OPENMM_IMAGE) -f Dockerfile.worker .

docker-push-atom-openmm:
	docker push $(ATOM_OPENMM_BASE_IMAGE)
	docker push $(ATOM_OPENMM_IMAGE)

docker-build-gcncmcmd:
	docker build -t $(GCNCMC_BASE_IMAGE) -f Dockerfile.worker-gcncmcmd-base .
	docker build --build-arg BASE_IMAGE=$(GCNCMC_BASE_IMAGE) -t $(GCNCMC_IMAGE) -f Dockerfile.worker .

docker-push-gcncmcmd:
	docker push $(GCNCMC_BASE_IMAGE)
	docker push $(GCNCMC_IMAGE)

docker-build-orchestrator:
	docker build -f Dockerfile.orchestrator -t $(ORCHESTRATOR_IMAGE) .

docker-push-orchestrator:
	docker push $(ORCHESTRATOR_IMAGE)

release-cli:
	@ver="$(VERSION)"; \
	if [ -z "$$ver" ]; then \
		cur=$$(sed -n 's/^version = "\(.*\)"/\1/p' pyproject.toml | head -n 1); \
		major=$$(echo "$$cur" | cut -d. -f1); \
		minor=$$(echo "$$cur" | cut -d. -f2); \
		patch=$$(echo "$$cur" | cut -d. -f3); \
		patch=$$((patch + 1)); \
		ver="$$major.$$minor.$$patch"; \
		while git rev-parse "v$$ver" >/dev/null 2>&1 || git ls-remote --exit-code --tags origin "refs/tags/v$$ver" >/dev/null 2>&1; do \
			patch=$$((patch + 1)); \
			ver="$$major.$$minor.$$patch"; \
		done; \
		echo "Auto bumping VERSION=$$ver"; \
	fi; \
	if [ "$(PUSH)" = "1" ]; then \
		./scripts/release_cli.sh "$$ver" --push; \
	else \
		./scripts/release_cli.sh "$$ver"; \
	fi

local-build-images:
	./scripts/local_build_images.sh

local-build-sif-or-sandbox:
	./scripts/local_build_sif_or_sandbox.sh

local-install-cli:
ifeq ($(BUILD),0)
	./scripts/local_install_cli.sh
else
	./scripts/local_install_cli.sh --build
endif

local-smoke:
	./scripts/local_smoke.sh
