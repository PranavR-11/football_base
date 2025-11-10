# Football Analytics - IONOS VPS Deployment Guide

Complete guide to deploying your football analytics application with:
- **Frontend**: Netlify (auto-deploys from GitHub)
- **Backend**: IONOS VPS (Ubuntu 24.04, 1 vCore, 1GB RAM)
- **Automation**: GitHub Actions for continuous deployment

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Quick Start (5 Steps)](#quick-start)
3. [Detailed Setup](#detailed-setup)
4. [DNS Configuration](#dns-configuration)
5. [Verification & Testing](#verification--testing)
6. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### What You Need

- [ ] IONOS VPS (1GB RAM, 1 vCore, Ubuntu 24.04) ✓
- [ ] Domain name (can buy from any registrar)
- [ ] GitHub account with this repository
- [ ] Cloudflare account (free) for DNS management
- [ ] OpenAI API key

### System Requirements

Your IONOS VPS meets the minimum requirements:
- **CPU**: 1 vCore ✓
- **RAM**: 1GB ✓
- **Storage**: 10GB NVMe SSD ✓
- **OS**: Ubuntu 24.04 ✓

---

## Quick Start

### Step 1: Get Your Domain & DNS

**Option A: Using Cloudflare (Recommended - FREE)**

1. Create a free Cloudflare account at https://cloudflare.com
2. Add your domain to Cloudflare
3. Update nameservers at your domain registrar to Cloudflare's
4. Get your Cloudflare API Token:
   - Go to https://dash.cloudflare.com/profile/api-tokens
   - Create Token → "Edit zone DNS" template
   - Select your domain
   - Save the token (starts with something like `abcd1234...`)
5. Get your Zone ID:
   - Go to your domain overview in Cloudflare
   - Copy the "Zone ID" from the right sidebar

**Option B: Using Your Registrar's DNS**

If you prefer to use your domain registrar's DNS (GoDaddy, Namecheap, etc.):
- You'll need to manually create an A record for `api.yourdomain.com` pointing to your VPS IP
- DNS auto-update won't work (but you can skip that feature)

---

### Step 2: Set Up GitHub Secrets

Go to your repository → Settings → Secrets and variables → Actions → New repository secret

Add these secrets:

| Secret Name | Value | Where to Find |
|------------|-------|---------------|
| `SSH_PRIVATE_KEY` | *See below* | Generate SSH key pair |
| `SSH_KNOWN_HOSTS` | *See below* | Run `ssh-keyscan YOUR_VPS_IP` |
| `SERVER_USER` | `deployer` | You'll create this user |
| `SERVER_HOST` | Your VPS IP | IONOS control panel |
| `SERVER_PATH` | `/home/deployer/football_base` | Server path |
| `OPENAI_API_KEY` | `sk-proj-...` | OpenAI dashboard |
| `MCP_API_KEY` | (if used) | Your MCP provider |
| `DOMAIN` | `api.yourdomain.com` | Your chosen subdomain |

**Generating SSH Keys (run on your local machine):**

```bash
# Generate SSH key pair
ssh-keygen -t ed25519 -C "github-deploy" -f ./github_deploy_key -N ""

# This creates two files:
# - github_deploy_key (PRIVATE - add to GitHub secret SSH_PRIVATE_KEY)
# - github_deploy_key.pub (PUBLIC - add to VPS later)

# Get the private key content:
cat ./github_deploy_key
# Copy entire output and paste into GitHub secret SSH_PRIVATE_KEY

# Get known hosts:
ssh-keyscan YOUR_VPS_IP > known_hosts
cat known_hosts
# Copy entire output and paste into GitHub secret SSH_KNOWN_HOSTS
```

---

### Step 3: Set Up VPS (One-Time Setup)

SSH into your VPS:

```bash
ssh root@YOUR_VPS_IP
# Enter password from IONOS control panel
```

Copy and paste this entire block to set up everything:

```bash
#!/bin/bash
set -e

echo "🚀 Setting up IONOS VPS for Football Analytics..."

# Create deployer user
adduser --gecos "" --disabled-password deployer
echo "deployer:CHOOSE_A_PASSWORD" | chpasswd
usermod -aG sudo deployer

# Update system
apt update && apt upgrade -y

# Install essentials
apt install -y git curl jq dnsutils ufw

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
usermod -aG docker deployer

# Install Docker Compose plugin
apt install -y docker-compose-plugin

# Configure firewall
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# Add SSH public key for deployer
mkdir -p /home/deployer/.ssh
chmod 700 /home/deployer/.ssh

# PASTE YOUR PUBLIC KEY HERE (from github_deploy_key.pub):
cat >> /home/deployer/.ssh/authorized_keys << 'EOF'
PASTE_YOUR_PUBLIC_KEY_HERE
EOF

chmod 600 /home/deployer/.ssh/authorized_keys
chown -R deployer:deployer /home/deployer/.ssh

# Clone repository as deployer
sudo -u deployer git clone https://github.com/YOUR_USERNAME/football_base.git /home/deployer/football_base

# Create data directories
mkdir -p /home/deployer/football_base/data/vectorstore
mkdir -p /home/deployer/football_base/models
chown -R deployer:deployer /home/deployer/football_base

# Make deploy script executable
chmod +x /home/deployer/football_base/deploy/ionos/deploy.sh
chmod +x /home/deployer/football_base/deploy/ionos/update_dns.sh

echo "✅ VPS setup complete!"
echo "Next: Upload your data files to /home/deployer/football_base/data/"
```

**Replace:**
- `CHOOSE_A_PASSWORD` with a strong password for the deployer user
- `PASTE_YOUR_PUBLIC_KEY_HERE` with the content of `github_deploy_key.pub`
- `YOUR_USERNAME` with your GitHub username

---

### Step 4: Upload Data Files to VPS

From your local machine, upload your data files:

```bash
# Upload CSV data
scp data/FINAL_with_rag.csv deployer@YOUR_VPS_IP:/home/deployer/football_base/data/

# Upload vectorstore (if you have it)
scp -r data/vectorstore/* deployer@YOUR_VPS_IP:/home/deployer/football_base/data/vectorstore/

# Upload model file (if you have it)
scp models/ridge_player_model.joblib deployer@YOUR_VPS_IP:/home/deployer/football_base/models/
```

---

### Step 5: Configure DNS Auto-Updater (Optional but Recommended)

SSH to VPS as deployer:

```bash
ssh deployer@YOUR_VPS_IP
cd /home/deployer/football_base/deploy/ionos
```

Create DNS configuration:

```bash
# Copy example and edit with your values
cp .env.dns.example .env.dns
nano .env.dns
```

Fill in:
```bash
CF_API_TOKEN=your_cloudflare_token_here
ZONE_ID=your_cloudflare_zone_id_here
RECORD_NAME=api.yourdomain.com
TTL=300
PROXIED=false
LOG_FILE=/var/log/dns-updater.log
```

Install and enable the DNS updater service:

```bash
# Copy systemd files
sudo cp dns-updater.service /etc/systemd/system/
sudo cp dns-updater.timer /etc/systemd/system/

# Create log file
sudo touch /var/log/dns-updater.log
sudo chown deployer:deployer /var/log/dns-updater.log

# Enable and start the timer
sudo systemctl daemon-reload
sudo systemctl enable dns-updater.timer
sudo systemctl start dns-updater.timer

# Test it manually first
./update_dns.sh

# Check status
sudo systemctl status dns-updater.timer
sudo journalctl -u dns-updater -f
```

---

## Detailed Setup

### DNS Configuration

#### Creating the A Record

**If using Cloudflare:**
1. Go to your domain in Cloudflare dashboard
2. Click "DNS" → "Add record"
3. Type: `A`
4. Name: `api` (for api.yourdomain.com)
5. IPv4 address: Your VPS IP (from IONOS)
6. TTL: 300 (5 minutes)
7. Proxy status: OFF (gray cloud) ← Important!
8. Click "Save"

**If using other DNS providers:**
- Log in to your DNS control panel
- Create an A record:
  - Host/Name: `api`
  - Points to: Your VPS IP
  - TTL: 300

**Verify DNS:**
```bash
dig +short api.yourdomain.com
# Should return your VPS IP
```

---

### Netlify Frontend Deployment

#### Option A: Netlify Dashboard (Easiest)

1. Go to https://app.netlify.com
2. Click "Add new site" → "Import an existing project"
3. Choose GitHub and select your repository
4. Configure build settings:
   - **Base directory**: `web`
   - **Build command**: `npm run build`
   - **Publish directory**: `web/.next`
5. Add environment variable:
   - **Key**: `NEXT_PUBLIC_WS_URL`
   - **Value**: `wss://api.yourdomain.com/ws/chat`
6. Click "Deploy site"

Netlify will now auto-deploy on every push to main!

#### Option B: Environment Variables

Add these in Netlify site settings → Build & deploy → Environment variables:

| Key | Value |
|-----|-------|
| `NEXT_PUBLIC_WS_URL` | `wss://api.yourdomain.com/ws/chat` |

---

## First Deployment

### Manual First Deploy (Recommended)

SSH to your VPS as deployer and run the first deployment manually:

```bash
ssh deployer@YOUR_VPS_IP
cd /home/deployer/football_base
./deploy/ionos/deploy.sh
```

Watch the logs:
```bash
cd deploy/ionos
docker compose logs -f
```

Check container status:
```bash
docker compose ps
```

### Trigger GitHub Actions Deploy

After the manual deploy works, push a change to test automation:

```bash
git commit --allow-empty -m "test: trigger deployment"
git push origin main
```

Go to GitHub → Actions tab and watch the deployment run!

---

## Verification & Testing

### 1. Check DNS

```bash
dig +short api.yourdomain.com
# Should return your VPS IP
```

### 2. Check Containers

```bash
ssh deployer@YOUR_VPS_IP
cd /home/deployer/football_base/deploy/ionos
docker compose ps
```

Expected output:
```
NAME                 STATUS          PORTS
football_api         Up X minutes    8000/tcp
football_caddy       Up X minutes    0.0.0.0:80->80/tcp, 0.0.0.0:443->443/tcp
```

### 3. Test API Health Endpoint

```bash
curl https://api.yourdomain.com/health
# Should return: {"status":"healthy"}
```

### 4. Test WebSocket from Frontend

1. Open your Netlify site URL
2. Open browser DevTools → Network tab → WS filter
3. Type a query in the chat
4. You should see: `wss://api.yourdomain.com/ws/chat` with status 101 (Switching Protocols)
5. Click the WS connection to see message frames

### 5. Full Integration Test

1. Open frontend (Netlify URL)
2. Status should show: 🟢 CONNECTED
3. Type a query: "Compare Messi and Ronaldo"
4. Should receive response with text and radar chart

---

## Troubleshooting

### Issue: DNS not resolving

**Check:**
```bash
dig +short api.yourdomain.com @8.8.8.8
nslookup api.yourdomain.com
```

**Fix:**
- Verify A record exists in DNS provider
- Wait 5-10 minutes for DNS propagation
- If using Cloudflare proxy (orange cloud), turn it OFF for initial setup

---

### Issue: Caddy can't get TLS certificate

**Symptoms:**
```
obtaining certificate: [...] challenge failed
```

**Check:**
```bash
# Verify DNS points to VPS
dig +short api.yourdomain.com

# Check if ports are open
sudo ufw status
sudo netstat -tulpn | grep -E ':(80|443)'
```

**Fix:**
1. Ensure DNS A record points to VPS IP
2. Ensure ports 80 and 443 are open:
   ```bash
   sudo ufw allow 80/tcp
   sudo ufw allow 443/tcp
   ```
3. If using Cloudflare proxy, disable it (gray cloud)
4. Check Caddy logs:
   ```bash
   docker compose logs caddy | grep -i error
   ```

---

### Issue: API container keeps restarting

**Check logs:**
```bash
docker compose logs api --tail=100
```

**Common causes:**
1. Missing OPENAI_API_KEY in .env
2. Missing data files in `/app/data/`
3. Out of memory (1GB RAM limit)

**Fix:**
```bash
# Check if .env exists
cat deploy/ionos/.env

# Check memory usage
docker stats

# Restart with fresh logs
docker compose down
docker compose up -d
docker compose logs -f api
```

---

### Issue: WebSocket connection fails

**Symptoms:**
- Frontend shows: 🔴 DISCONNECTED
- Browser console: `WebSocket connection failed`

**Check:**
1. Backend is running:
   ```bash
   curl https://api.yourdomain.com/health
   ```

2. WebSocket endpoint is accessible:
   ```bash
   curl -i -N -H "Connection: Upgrade" -H "Upgrade: websocket" \
     -H "Sec-WebSocket-Version: 13" -H "Sec-WebSocket-Key: test" \
     https://api.yourdomain.com/ws/chat
   ```

3. Frontend has correct URL:
   - Check Netlify environment variables
   - `NEXT_PUBLIC_WS_URL` should be `wss://api.yourdomain.com/ws/chat`

**Fix:**
- Redeploy Netlify site after updating environment variable
- Check Caddyfile has WebSocket proxying enabled
- Verify no firewall blocking WSS

---

### Issue: GitHub Actions deployment fails

**Check the Actions logs:**
- Go to GitHub → Actions tab
- Click the failed workflow run
- Expand each step to see errors

**Common issues:**

1. **SSH connection failed**
   - Verify `SSH_PRIVATE_KEY` secret is correct (full file content)
   - Verify `SSH_KNOWN_HOSTS` is correct
   - Test manually: `ssh deployer@YOUR_VPS_IP`

2. **Permission denied**
   - Verify deployer user has sudo access
   - Verify deploy.sh is executable: `chmod +x deploy/ionos/deploy.sh`

3. **Docker permission denied**
   - Verify deployer is in docker group: `sudo usermod -aG docker deployer`
   - Log out and back in for group changes to take effect

---

### Issue: Out of memory (OOM) on 1GB RAM VPS

**Symptoms:**
- Containers getting killed
- `docker compose ps` shows containers exited (137)

**Check memory:**
```bash
free -h
docker stats
```

**Solutions:**

1. **Add swap space:**
   ```bash
   sudo fallocate -l 2G /swapfile
   sudo chmod 600 /swapfile
   sudo mkswap /swapfile
   sudo swapon /swapfile
   echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
   ```

2. **Optimize Docker limits** (already set in docker-compose.yml):
   - API container limited to 750MB
   - Caddy container limited to 128MB

3. **Restart containers:**
   ```bash
   docker compose down
   docker system prune -f
   docker compose up -d
   ```

---

## Useful Commands

### Docker Management

```bash
# View all containers
docker compose ps

# View logs
docker compose logs -f api
docker compose logs -f caddy

# Restart containers
docker compose restart

# Rebuild and restart
docker compose up -d --build

# Stop all containers
docker compose down

# Clean up old images
docker system prune -a -f
```

### Server Management

```bash
# Check disk space
df -h

# Check memory usage
free -h

# Check running processes
htop

# Check firewall status
sudo ufw status

# View systemd service logs
sudo journalctl -u dns-updater -f
```

### DNS Management

```bash
# Test DNS resolution
dig +short api.yourdomain.com

# Test with specific DNS server
dig @8.8.8.8 api.yourdomain.com

# Check nameservers
dig NS yourdomain.com

# Manual DNS update (if auto-updater is set up)
cd /home/deployer/football_base/deploy/ionos
./update_dns.sh
```

---

## Architecture Overview

```
┌─────────────┐
│   Browser   │
└──────┬──────┘
       │
       │ HTTPS/WSS
       ▼
┌─────────────────┐
│  Netlify CDN    │  (Frontend - Next.js)
│  yourdomain.com │
└─────────────────┘
       │
       │ WebSocket (wss://)
       ▼
┌───────────────────────────────────┐
│  IONOS VPS (Ubuntu 24.04)         │
│  api.yourdomain.com               │
│                                   │
│  ┌─────────────────────────────┐ │
│  │ Caddy (Reverse Proxy + TLS) │ │
│  │ :80, :443                   │ │
│  └─────────┬───────────────────┘ │
│            │                      │
│            ▼                      │
│  ┌─────────────────────────────┐ │
│  │ FastAPI Backend             │ │
│  │ :8000                       │ │
│  │ - WebSocket handler         │ │
│  │ - LangChain agent           │ │
│  │ - Chart generation          │ │
│  └─────────────────────────────┘ │
│                                   │
│  ┌─────────────────────────────┐ │
│  │ Data                        │ │
│  │ - CSV files                 │ │
│  │ - Vector store              │ │
│  │ - ML models                 │ │
│  └─────────────────────────────┘ │
└───────────────────────────────────┘
       │
       │ API calls
       ▼
┌─────────────────┐
│  OpenAI API     │
└─────────────────┘
```

---

## Security Best Practices

1. **Never commit secrets to Git**
   - Use `.env` files (already in `.gitignore`)
   - Store secrets in GitHub Secrets for CI/CD

2. **Rotate API keys regularly**
   - OpenAI API keys
   - Cloudflare API tokens

3. **Keep VPS updated**
   ```bash
   sudo apt update && sudo apt upgrade -y
   ```

4. **Monitor logs for suspicious activity**
   ```bash
   sudo journalctl -f
   docker compose logs -f
   ```

5. **Use firewall (already configured)**
   ```bash
   sudo ufw status
   ```

6. **Disable root SSH login** (optional but recommended):
   ```bash
   sudo nano /etc/ssh/sshd_config
   # Set: PermitRootLogin no
   sudo systemctl restart sshd
   ```

---

## Cost Breakdown

| Service | Plan | Cost |
|---------|------|------|
| **IONOS VPS** | 1GB RAM, 1 vCore | €2-4/month |
| **Netlify** | Free tier | $0 |
| **Cloudflare** | Free tier | $0 |
| **Domain** | .com domain | ~$12/year |
| **OpenAI API** | Pay-as-you-go | Usage-based |

**Total**: ~€4-6/month + OpenAI usage

---

## Next Steps After Deployment

1. **Set up monitoring**
   - Configure Uptime Robot or similar for uptime monitoring
   - Set up email alerts for container failures

2. **Optimize performance**
   - Enable gzip compression (already in Caddyfile)
   - Add Redis for caching (if needed)
   - Consider upgrading VPS if memory becomes an issue

3. **Add features**
   - User authentication
   - Rate limiting
   - Analytics tracking

4. **Backup strategy**
   - Set up automated backups of data directory
   - Export Docker volumes regularly

---

## Support & Resources

- **IONOS Support**: https://www.ionos.com/help
- **Cloudflare Docs**: https://developers.cloudflare.com
- **Netlify Docs**: https://docs.netlify.com
- **Docker Docs**: https://docs.docker.com
- **Caddy Docs**: https://caddyserver.com/docs

---

## License

This deployment configuration is part of the Football Analytics project.

---

**Happy Deploying! ⚽**
