.PHONY: ui docker-build docker-push release-cli setup-hooks

setup-hooks:
	git config core.hooksPath .githooks
	chmod +x .githooks/pre-commit .githooks/pre-push

ORG ?= your-org
IMAGE ?= ghcr.io/$(ORG)/relaymd-worker:latest

ui:
	uv run --with-requirements ui/requirements.txt streamlit run ui/dashboard.py

docker-build:
	docker build -t $(IMAGE) .

docker-push:
	docker push $(IMAGE)

release-cli:
	@test -n "$(VERSION)" || (echo "Usage: make release-cli VERSION=X.Y.Z [PUSH=1]"; exit 1)
	@if [ "$(PUSH)" = "1" ]; then \
		./scripts/release_cli.sh "$(VERSION)" --push; \
	else \
		./scripts/release_cli.sh "$(VERSION)"; \
	fi
