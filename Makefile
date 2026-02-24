.PHONY: ui docker-build docker-push

ORG ?= your-org
IMAGE ?= ghcr.io/$(ORG)/relaymd-worker:latest

ui:
	streamlit run ui/dashboard.py

docker-build:
	docker build -t $(IMAGE) .

docker-push:
	docker push $(IMAGE)
