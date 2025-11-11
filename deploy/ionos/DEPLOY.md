# Football Analytics - IONOS Deployment Guide

Complete guide to deploying your football analytics application with:
- **Frontend**: Netlify (auto-deploys from GitHub)
- **Backend**: IONOS VPS (Ubuntu 24.04, 1 vCore, 1GB RAM)
- **DNS**: IONOS DNS (manual A record)
- **CI/CD**: GitHub Actions for continuous deployment

---

## What You Have

✅ IONOS VPS: 1 vCore CPU, 1GB RAM, 10GB NVMe SSD, Ubuntu 24.04

---

## Quick Start (3 Main Steps)

### Step 1: Set Up GitHub Secrets

Go to: **GitHub Repository → Settings → Secrets and variables → Actions → New repository secret**

Add these 7 secrets:

| Secret Name | Value | How to Get |
|------------|-------|------------|
| **SSH_PRIVATE_KEY** | *See below* | Generate SSH key pair |
| **SSH_KNOWN_HOSTS** | *See below* | Run `ssh-keyscan YOUR_VPS_IP` |
| **SERVER_USER** | `deployer` | Fixed value |
| **SERVER_HOST** | Your VPS IP | IONOS control panel |
| **SERVER_PATH** | `/home/deployer/football_base` | Fixed value |
| **OPENAI_API_KEY** | `sk-proj-...` | OpenAI dashboard |
| **DOMAIN** | `api.yourdomain.com` | Your domain |

**Generate SSH Keys (run on your Mac):**

```bash
# Generate key pair
ssh-keygen -t ed25519 -C "github-deploy" -f ./github_deploy_key -N ""

# Show private key (copy this to SSH_PRIVATE_KEY secret)
cat ./github_deploy_key

# Show public key (you'll need this for the VPS)
cat ./github_deploy_key.pub

# Get known hosts (copy this to SSH_KNOWN_HOSTS secret)
ssh-keyscan YOUR_VPS_IP
```

---

### Step 2: Set Up IONOS VPS

SSH into your VPS:

```bash
ssh root@YOUR_VPS_IP
# (Use password from IONOS control panel)
```

**Copy and paste this entire script:**

```bash
#!/bin/bash
set -e

echo "🚀 Setting up IONOS VPS..."

# Create deployer user
adduser --gecos "" --disabled-password deployer
echo "deployer:YOUR_STRONG_PASSWORD_HERE" | chpasswd
usermod -aG sudo deployer

# Update system
apt update && apt upgrade -y

# Install essentials
apt install -y git curl jq ufw

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
usermod -aG docker deployer
apt install -y docker-compose-plugin

# Configure firewall
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# Set up SSH for deployer
mkdir -p /home/deployer/.ssh
chmod 700 /home/deployer/.ssh

# ADD YOUR PUBLIC KEY HERE (from github_deploy_key.pub)
cat >> /home/deployer/.ssh/authorized_keys << 'EOF'
ssh-ed25519 PASTE_YOUR_PUBLIC_KEY_HERE your-email@example.com
EOF

chmod 600 /home/deployer/.ssh/authorized_keys
chown -R deployer:deployer /home/deployer/.ssh

# Clone repository
sudo -u deployer git clone https://github.com/YOUR_GITHUB_USERNAME/football_base.git /home/deployer/football_base

# Create directories
mkdir -p /home/deployer/football_base/data/vectorstore
mkdir -p /home/deployer/football_base/models
chown -R deployer:deployer /home/deployer/football_base

# Make scripts executable
chmod +x /home/deployer/football_base/deploy/ionos/deploy.sh

echo "✅ Setup complete!"
```

**Before running, replace:**
- `YOUR_STRONG_PASSWORD_HERE` with a strong password
- `PASTE_YOUR_PUBLIC_KEY_HERE` with content of `github_deploy_key.pub`
- `YOUR_GITHUB_USERNAME` with your GitHub username

---

### Step 3: Set Up DNS

#### In IONOS Control Panel:

1. Go to **Domains & SSL** → **Your Domain** → **DNS**
2. Click **Add Record**
3. Create A record:
   - **Type**: A
   - **Host**: `api` (for api.yourdomain.com)
   - **Points to**: Your VPS IP (e.g., 12.34.56.78)
   - **TTL**: 300 (5 minutes)
4. Click **Save**

#### Verify DNS:

```bash
# Wait 5 minutes, then check:
dig +short api.yourdomain.com
# Should return your VPS IP
```

---

## Upload Data to VPS

From your Mac, upload data files:

```bash
# Upload CSV data
scp data/FINAL_with_rag.csv deployer@YOUR_VPS_IP:/home/deployer/football_base/data/

# Upload vectorstore (if you have it)
scp -r data/vectorstore/* deployer@YOUR_VPS_IP:/home/deployer/football_base/data/vectorstore/

# Upload model (if you have it)
scp models/ridge_player_model.joblib deployer@YOUR_VPS_IP:/home/deployer/football_base/models/
```

---

## First Deployment

### Manual Test (Recommended First)

SSH to VPS as deployer:

```bash
ssh deployer@YOUR_VPS_IP
cd /home/deployer/football_base/deploy/ionos
```

Create `.env` file:

```bash
nano .env
```

Add:
```bash
DOMAIN=api.yourdomain.com
OPENAI_API_KEY=sk-proj-YOUR_REAL_KEY_HERE
MCP_API_KEY=your_mcp_key_if_used
DATA_PATH=/app/data/FINAL_with_rag.csv
VECTORSTORE_DIR=/app/data/vectorstore
MODEL_PATH=/app/models/ridge_player_model.joblib
AGENT_DEBUG=False
```

Save (Ctrl+X, Y, Enter) and deploy:

```bash
cd /home/deployer/football_base
./deploy/ionos/deploy.sh
```

**Watch the logs:**
```bash
cd deploy/ionos
docker compose logs -f
```

You should see:
- Caddy getting TLS certificate
- API container starting successfully

**Check containers:**
```bash
docker compose ps
```

Expected:
```
NAME                 STATUS          PORTS
football_api         Up              8000/tcp
football_caddy       Up              0.0.0.0:80->80/tcp, 0.0.0.0:443->443/tcp
```

---

### Test API:

```bash
curl https://api.yourdomain.com/health
```

Should return:
```json
{"status":"healthy"}
```

---

## Set Up Netlify (Frontend)

### Deploy Frontend:

1. Go to https://app.netlify.com
2. Click **Add new site** → **Import an existing project**
3. Choose **GitHub** → Select your repository
4. Configure:
   - **Base directory**: `web`
   - **Build command**: `npm run build`
   - **Publish directory**: `web/.next`
5. Add environment variable:
   - **Key**: `NEXT_PUBLIC_WS_URL`
   - **Value**: `wss://api.yourdomain.com/ws/chat`
6. Click **Deploy site**

Netlify will now auto-deploy on every push to main!

---

## Automatic GitHub Actions Deployment

After your first manual deployment works, GitHub Actions will take over.

**How it works:**
1. You push code to `main` branch
2. GitHub Actions triggers
3. Action SSHs to your VPS
4. Runs `deploy.sh` to pull code and restart containers
5. Backend is updated!

**View deployments:**
- Go to GitHub → Actions tab
- See deployment logs in real-time

---

## Verification Checklist

### 1. DNS Check
```bash
dig +short api.yourdomain.com
# Should show your VPS IP
```

### 2. HTTPS Check
```bash
curl -I https://api.yourdomain.com/health
# Should show: HTTP/2 200
```

### 3. WebSocket Check
1. Open Netlify site in browser
2. Open DevTools → Network tab → WS filter
3. Type a query
4. Should see: `wss://api.yourdomain.com/ws/chat` with status 101

### 4. Full Integration Test
1. Open frontend
2. Status: 🟢 CONNECTED
3. Ask: "Compare Messi and Ronaldo"
4. Should get text response + radar chart

---

## Common Issues & Fixes

### Issue: Caddy Can't Get TLS Certificate

**Symptom:**
```
obtaining certificate: challenge failed
```

**Fix:**
1. Verify DNS points to VPS:
   ```bash
   dig +short api.yourdomain.com
   ```
2. Ensure ports 80 & 443 are open:
   ```bash
   sudo ufw status
   ```
3. Check Caddy logs:
   ```bash
   docker compose logs caddy
   ```

---

### Issue: Out of Memory (1GB RAM)

**Symptom:**
- Containers getting killed
- Exit code 137

**Fix - Add Swap:**
```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
free -h  # Verify swap is active
```

---

### Issue: WebSocket Connection Fails

**Check:**
1. Backend running: `curl https://api.yourdomain.com/health`
2. Netlify env var set: `NEXT_PUBLIC_WS_URL=wss://api.yourdomain.com/ws/chat`
3. Redeploy Netlify site after changing env var

---

### Issue: GitHub Actions Fails

**Common causes:**
1. **SSH_PRIVATE_KEY** not set correctly (must be full file content)
2. **SSH_KNOWN_HOSTS** not set correctly
3. Deployer user not in docker group:
   ```bash
   sudo usermod -aG docker deployer
   # Log out and back in
   ```

---

## Useful Commands

### On VPS:

```bash
# View logs
cd /home/deployer/football_base/deploy/ionos
docker compose logs -f api
docker compose logs -f caddy

# Restart containers
docker compose restart

# Rebuild
docker compose up -d --build

# Check status
docker compose ps

# Check memory
free -h
docker stats
```

### On Your Mac:

```bash
# Test SSH
ssh deployer@YOUR_VPS_IP

# Upload file
scp localfile.txt deployer@YOUR_VPS_IP:/home/deployer/football_base/data/

# View remote logs
ssh deployer@YOUR_VPS_IP "cd /home/deployer/football_base/deploy/ionos && docker compose logs --tail=100"
```

---

## Architecture

```
User Browser
     ↓
Netlify (Frontend)
     ↓ WebSocket (wss://)
IONOS VPS:
  → Caddy (ports 80, 443) - Auto HTTPS
    → FastAPI (port 8000) - Backend API
      → OpenAI API
```

---

## Cost Summary

| Service | Cost |
|---------|------|
| IONOS VPS | €2-4/month |
| Netlify | Free |
| Domain | ~€12/year |
| OpenAI API | Usage-based |

**Total: ~€4-6/month + API usage**

---

## Next Steps

1. ✅ Push code → GitHub Actions auto-deploys
2. ✅ Monitor uptime with UptimeRobot (free)
3. ✅ Set up backups of `/home/deployer/football_base/data`
4. Optional: Add authentication to frontend
5. Optional: Upgrade VPS if memory becomes an issue

---

## Support

- **IONOS**: https://www.ionos.com/help
- **Netlify**: https://docs.netlify.com
- **Docker**: https://docs.docker.com
- **Caddy**: https://caddyserver.com/docs

---

**Happy Deploying! ⚽**
