.PHONY: ui docker-build docker-push deploy-orchestrator

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
