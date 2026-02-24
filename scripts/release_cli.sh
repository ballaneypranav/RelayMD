#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'EOF'
Usage:
  scripts/release_cli.sh <version> [--push]

Examples:
  scripts/release_cli.sh 0.1.1
  scripts/release_cli.sh 0.1.1 --push
EOF
}

if [[ $# -lt 1 || $# -gt 2 ]]; then
    usage
    exit 1
fi

VERSION="$1"
PUSH=0
if [[ "${2:-}" == "--push" ]]; then
    PUSH=1
elif [[ $# -eq 2 ]]; then
    usage
    exit 1
fi

if ! [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "Version must match semver format X.Y.Z"
    exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYPROJECT_PATH="packages/relaymd-cli/pyproject.toml"
INIT_PATH="packages/relaymd-cli/src/relaymd/cli/__init__.py"

CURRENT_VERSION="$(sed -n 's/^version = "\(.*\)"/\1/p' "$PYPROJECT_PATH" | head -n 1)"
if [[ -z "$CURRENT_VERSION" ]]; then
    echo "Failed to read current version from $PYPROJECT_PATH"
    exit 1
fi

if [[ "$CURRENT_VERSION" == "$VERSION" ]]; then
    echo "Version is already $VERSION"
    exit 1
fi

if git rev-parse "v$VERSION" >/dev/null 2>&1; then
    echo "Tag v$VERSION already exists"
    exit 1
fi

sed -i "s/^version = \".*\"$/version = \"$VERSION\"/" "$PYPROJECT_PATH"
sed -i "s/^__version__ = \".*\"$/__version__ = \"$VERSION\"/" "$INIT_PATH"

UV_CACHE_DIR=/tmp/uv-cache uv lock

git add "$PYPROJECT_PATH" "$INIT_PATH" uv.lock
git commit -m "Bump relaymd-cli version to $VERSION"
git tag "v$VERSION"

if [[ "$PUSH" -eq 1 ]]; then
    git push origin main
    git push origin "v$VERSION"
fi

echo "Released relaymd-cli $VERSION"
if [[ "$PUSH" -eq 0 ]]; then
    echo "Next: git push origin main && git push origin v$VERSION"
fi
