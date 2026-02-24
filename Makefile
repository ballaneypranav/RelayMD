.PHONY: ui docker-build docker-push deploy-orchestrator release-cli

ORG ?= your-org
IMAGE ?= ghcr.io/$(ORG)/relaymd-worker:latest

ui:
	streamlit run ui/dashboard.py

docker-build:
	docker build -t $(IMAGE) .

docker-push:
	docker push $(IMAGE)

deploy-orchestrator:
	mkdir -p ~/.config/systemd/user
	cp deploy/systemd/relaymd-orchestrator.service ~/.config/systemd/user/relaymd-orchestrator.service
	systemctl --user daemon-reload
	systemctl --user enable relaymd-orchestrator
	systemctl --user start relaymd-orchestrator

release-cli:
	@test -n "$(VERSION)" || (echo "Usage: make release-cli VERSION=X.Y.Z [PUSH=1]"; exit 1)
	@if [ "$(PUSH)" = "1" ]; then \
		./scripts/release_cli.sh "$(VERSION)" --push; \
	else \
		./scripts/release_cli.sh "$(VERSION)"; \
	fi
