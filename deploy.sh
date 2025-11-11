#!/usr/bin/env bash
set -euo pipefail

# Deploy script (keeps working dir at repo root)
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

# Pick docker-compose file (prefer root then deploy/ionos folder)
if [ -f "$REPO_ROOT/docker-compose.yml" ]; then
  COMPOSE="-f $REPO_ROOT/docker-compose.yml"
elif [ -f "$REPO_ROOT/deploy/ionos/docker-compose.yml" ]; then
  COMPOSE="-f $REPO_ROOT/deploy/ionos/docker-compose.yml"
else
  echo "ERROR: No docker-compose.yml found in repo root or deploy/ionos/"
  exit 2
fi
echo "Using compose file: $COMPOSE"

git fetch --all --prune
git reset --hard origin/main
