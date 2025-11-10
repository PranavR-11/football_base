#!/usr/bin/env bash
set -euo pipefail

###############################################################################
# Server Deployment Script
#
# This script pulls the latest code from GitHub and rebuilds/restarts
# Docker containers. It's designed to be called by GitHub Actions or manually.
#
# Usage:
#   cd /home/deployer/football_base
#   ./deploy/ionos/deploy.sh
###############################################################################

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $*"
}

error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ERROR:${NC} $*" >&2
}

warn() {
    echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')] WARNING:${NC} $*"
}

# Change to repository root
cd "$(dirname "$0")/../.."
REPO_ROOT=$(pwd)

log "Starting deployment in $REPO_ROOT"

# Verify we're in a git repository
if [[ ! -d .git ]]; then
    error "Not a git repository"
    exit 1
fi

# Fetch latest code
log "Fetching latest code from origin..."
git fetch --all --prune

# Get current branch
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
log "Current branch: $CURRENT_BRANCH"

# Reset to origin/main (or current branch)
log "Resetting to origin/$CURRENT_BRANCH..."
git reset --hard "origin/$CURRENT_BRANCH"

# Show current commit
CURRENT_COMMIT=$(git rev-parse --short HEAD)
COMMIT_MSG=$(git log -1 --pretty=%B)
log "Now at commit: $CURRENT_COMMIT"
log "Commit message: $COMMIT_MSG"

# Verify required files exist
if [[ ! -f deploy/ionos/docker-compose.yml ]]; then
    error "docker-compose.yml not found"
    exit 1
fi

if [[ ! -f deploy/ionos/.env ]]; then
    warn ".env file not found - using .env.example as template"
    if [[ -f deploy/ionos/.env.example ]]; then
        cp deploy/ionos/.env.example deploy/ionos/.env
        warn "Please edit deploy/ionos/.env with real values"
    fi
fi

# Change to deployment directory
cd deploy/ionos

# Pull latest images (if any are from registry)
log "Pulling latest images..."
docker compose pull || warn "No images to pull (using local builds)"

# Build and restart containers
log "Building and restarting containers..."
docker compose up -d --build --remove-orphans

# Show container status
log "Container status:"
docker compose ps

# Show recent logs
log "Recent logs from API:"
docker compose logs --tail=50 api

log "Recent logs from Caddy:"
docker compose logs --tail=20 caddy

# Cleanup old images
log "Cleaning up old Docker images..."
docker image prune -f

log "Deployment complete!"
log "API should be available at: https://\${DOMAIN:-api.yourdomain.com}"
log ""
log "To view logs:"
log "  docker compose -f $REPO_ROOT/deploy/ionos/docker-compose.yml logs -f"
log ""
log "To check status:"
log "  docker compose -f $REPO_ROOT/deploy/ionos/docker-compose.yml ps"
