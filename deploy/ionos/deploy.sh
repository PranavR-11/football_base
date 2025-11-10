#!/bin/bash
# Deployment script for IONOS server

set -e

SERVER_HOST="${SERVER_HOST:-footballbase.duckdns.org}"
SERVER_USER="${SERVER_USER:-root}"
DEPLOY_DIR="/root/football_base"

echo "🚀 Deploying to $SERVER_USER@$SERVER_HOST"

# Check if we have SSH access
if ! ssh -o ConnectTimeout=5 "$SERVER_USER@$SERVER_HOST" "echo '✅ SSH connection successful'" 2>/dev/null; then
    echo "❌ Cannot connect to server. Please check your SSH configuration."
    exit 1
fi

echo "📦 Creating deployment archive..."
cd "$(dirname "$0")/../.."
tar czf /tmp/football_deploy.tar.gz \
    --exclude='node_modules' \
    --exclude='.git' \
    --exclude='*.pyc' \
    --exclude='__pycache__' \
    --exclude='.next' \
    --exclude='web/.next' \
    --exclude='web/node_modules' \
    .

echo "📤 Uploading files to server..."
scp /tmp/football_deploy.tar.gz "$SERVER_USER@$SERVER_HOST:/tmp/"

echo "🔧 Deploying on server..."
ssh "$SERVER_USER@$SERVER_HOST" << 'ENDSSH'
set -e

# Extract files
cd /root
mkdir -p football_base
cd football_base
tar xzf /tmp/football_deploy.tar.gz
rm /tmp/football_deploy.tar.gz

echo "🏗️ Rebuilding and restarting services..."
cd deploy/ionos

# Stop services
docker compose down

# Rebuild and start
docker compose build --no-cache
docker compose up -d

# Wait for services to be healthy
echo "⏳ Waiting for services to start..."
sleep 10

# Check status
docker compose ps
docker compose logs --tail=20

echo "✅ Deployment complete!"
echo "🔍 Checking health..."
curl -s http://localhost/health | jq . || echo "Health check failed"
ENDSSH

echo ""
echo "✅ Deployment successful!"
echo "🌐 Your app should be available at: https://$SERVER_HOST"
echo ""
echo "To view logs, run:"
echo "  ssh $SERVER_USER@$SERVER_HOST 'cd $DEPLOY_DIR/deploy/ionos && docker compose logs -f api'"
