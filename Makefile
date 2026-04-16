.PHONY: frontend-build docker-build docker-push docker-build-worker docker-push-worker docker-build-orchestrator docker-push-orchestrator release-cli setup-hooks

setup-hooks:
	git config core.hooksPath .githooks
	chmod +x .githooks/pre-commit .githooks/pre-push

ORG ?= your-org
BASE_IMAGE ?= ghcr.io/$(ORG)/relaymd-base:latest
WORKER_IMAGE ?= ghcr.io/$(ORG)/relaymd-worker:latest
ORCHESTRATOR_IMAGE ?= ghcr.io/$(ORG)/relaymd-orchestrator:latest
IMAGE ?= $(WORKER_IMAGE)

frontend-build:
	cd frontend && npm --cache ./.npm install
	cd frontend && npm --cache ./.npm run build

docker-build-base:
	docker build -t $(BASE_IMAGE) -f Dockerfile.base .

docker-push-base:
	docker push $(BASE_IMAGE)

docker-build:
	docker build --build-arg BASE_IMAGE=$(BASE_IMAGE) -t $(IMAGE) .

docker-push:
	docker push $(IMAGE)

docker-build-worker:
	docker build --build-arg BASE_IMAGE=$(BASE_IMAGE) -t $(IMAGE) .

docker-push-worker:
	docker push $(IMAGE)

docker-build-orchestrator:
	docker build -f Dockerfile.orchestrator -t $(ORCHESTRATOR_IMAGE) .

docker-push-orchestrator:
	docker push $(ORCHESTRATOR_IMAGE)

release-cli:
	@test -n "$(VERSION)" || (echo "Usage: make release-cli VERSION=X.Y.Z [PUSH=1]"; exit 1)
	@if [ "$(PUSH)" = "1" ]; then \
		./scripts/release_cli.sh "$(VERSION)" --push; \
	else \
		./scripts/release_cli.sh "$(VERSION)"; \
	fi
