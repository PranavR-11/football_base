# Football Base - Your Deployment Checklist

## ✅ What You Have

- **Domain**: `footballbase.duckdns.org` ✅
- **VPS IP**: `96.240.7.90` ✅
- **VPS**: IONOS Ubuntu 24.04, 1GB RAM, 1 vCore ✅
- **Repository**: `github.com/PranavR-11/football_base` ✅

---

## 📋 Deployment Steps

### Step 1: Generate SSH Keys (On Your Mac)

```bash
# Generate SSH key pair
ssh-keygen -t ed25519 -C "github-deploy" -f ./github_deploy_key -N ""

# This creates:
# - github_deploy_key (PRIVATE - for GitHub secret)
# - github_deploy_key.pub (PUBLIC - for VPS)
```

**Save these outputs:**

```bash
# 1. Private key (copy for GitHub secret SSH_PRIVATE_KEY)
cat ./github_deploy_key

# 2. Public key (copy for VPS setup script)
cat ./github_deploy_key.pub

# 3. Known hosts (copy for GitHub secret SSH_KNOWN_HOSTS)
ssh-keyscan 96.240.7.90
```

---

### Step 2: Add GitHub Secrets

Go to: https://github.com/PranavR-11/football_base/settings/secrets/actions/new

Add these 7 secrets:

| Secret Name | Your Value |
|------------|------------|
| **SSH_PRIVATE_KEY** | Output from `cat ./github_deploy_key` |
| **SSH_KNOWN_HOSTS** | Output from `ssh-keyscan 96.240.7.90` |
| **SERVER_USER** | `deployer` |
| **SERVER_HOST** | `96.240.7.90` |
| **SERVER_PATH** | `/home/deployer/football_base` |
| **OPENAI_API_KEY** | Your OpenAI API key |
| **DOMAIN** | `footballbase.duckdns.org` |

---

### Step 3: Set Up VPS

**SSH to your VPS:**

```bash
ssh root@96.240.7.90
# Enter password from IONOS control panel
```

**Run this setup script:**

```bash
#!/bin/bash
set -e

echo "🚀 Setting up IONOS VPS for Football Base..."

# Create deployer user
adduser --gecos "" --disabled-password deployer
echo "deployer:YOUR_PASSWORD_HERE" | chpasswd
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

# ADD YOUR PUBLIC KEY (paste output from: cat ./github_deploy_key.pub)
cat >> /home/deployer/.ssh/authorized_keys << 'EOF'
PASTE_YOUR_PUBLIC_KEY_HERE
EOF

chmod 600 /home/deployer/.ssh/authorized_keys
chown -R deployer:deployer /home/deployer/.ssh

# Clone repository
sudo -u deployer git clone https://github.com/PranavR-11/football_base.git /home/deployer/football_base

# Create directories
mkdir -p /home/deployer/football_base/data/vectorstore
mkdir -p /home/deployer/football_base/models
chown -R deployer:deployer /home/deployer/football_base

# Make scripts executable
chmod +x /home/deployer/football_base/deploy/ionos/deploy.sh

echo "✅ VPS setup complete!"
echo "Next: Upload data files and deploy"
```

**Before running, replace:**
- `YOUR_PASSWORD_HERE` with a strong password (save it!)
- `PASTE_YOUR_PUBLIC_KEY_HERE` with output from `cat ./github_deploy_key.pub`

---

### Step 4: Upload Data Files

**From your Mac:**

```bash
# Upload CSV
scp data/FINAL_with_rag.csv deployer@96.240.7.90:/home/deployer/football_base/data/

# Upload vectorstore (if you have it)
scp -r data/vectorstore/* deployer@96.240.7.90:/home/deployer/football_base/data/vectorstore/

# Upload model (if you have it)
scp models/ridge_player_model.joblib deployer@96.240.7.90:/home/deployer/football_base/models/
```

---

### Step 5: First Deployment

**SSH to VPS as deployer:**

```bash
ssh deployer@96.240.7.90
cd /home/deployer/football_base/deploy/ionos
```

**Create `.env` file:**

```bash
nano .env
```

**Add this content:**

```bash
DOMAIN=footballbase.duckdns.org
OPENAI_API_KEY=your_openai_api_key_here
MCP_API_KEY=your_mcp_key_if_needed
DATA_PATH=/app/data/FINAL_with_rag.csv
VECTORSTORE_DIR=/app/data/vectorstore
MODEL_PATH=/app/models/ridge_player_model.joblib
AGENT_DEBUG=False
```

Save (Ctrl+X, Y, Enter)

**Deploy:**

```bash
cd /home/deployer/football_base
./deploy/ionos/deploy.sh
```

**Watch logs:**

```bash
cd deploy/ionos
docker compose logs -f
```

Wait for:
- ✅ Caddy gets TLS certificate for `footballbase.duckdns.org`
- ✅ API container starts successfully

**Check containers:**

```bash
docker compose ps
```

Expected output:
```
NAME                 STATUS          PORTS
football_api         Up              8000/tcp
football_caddy       Up              0.0.0.0:80->80/tcp, 0.0.0.0:443->443/tcp
```

---

### Step 6: Test Backend

**From your Mac:**

```bash
# Test health endpoint
curl https://footballbase.duckdns.org/health

# Should return:
# {"status":"healthy"}
```

**If you get an error:**
- Wait 1-2 minutes for Caddy to get TLS certificate
- Check logs: `docker compose logs caddy`

---

### Step 7: Set Up Netlify

**Deploy frontend:**

1. Go to https://app.netlify.com
2. Click **Add new site** → **Import an existing project**
3. Choose **GitHub** → Select `PranavR-11/football_base`
4. Configure:
   - **Base directory**: `web`
   - **Build command**: `npm run build`
   - **Publish directory**: `web/.next`
5. **Add environment variable:**
   - **Key**: `NEXT_PUBLIC_WS_URL`
   - **Value**: `wss://footballbase.duckdns.org/ws/chat`
6. Click **Deploy site**

Netlify will build and deploy your frontend!

---

### Step 8: Verify Full Stack

**Once Netlify deployment completes:**

1. Open your Netlify site URL (e.g., `https://your-app.netlify.app`)
2. Check connection status: Should show 🟢 **CONNECTED**
3. Type a query: "Compare Messi and Ronaldo"
4. Should receive:
   - Text comparison
   - Radar chart image

**Open DevTools → Network → WS:**
- Should see: `wss://footballbase.duckdns.org/ws/chat`
- Status: 101 Switching Protocols
- Frames: Request and response messages

---

## ✅ Deployment Complete!

### Your URLs:

- **Frontend**: `https://your-app.netlify.app` (Netlify will provide)
- **Backend API**: `https://footballbase.duckdns.org`
- **Health Check**: `https://footballbase.duckdns.org/health`

### What Happens Next:

**Every time you push to `main` branch:**
1. GitHub Actions triggers
2. Backend auto-deploys to VPS via SSH
3. Netlify auto-deploys frontend

**View deployments:**
- Backend: https://github.com/PranavR-11/football_base/actions
- Frontend: Netlify dashboard

---

## 🔧 Useful Commands

### On VPS:

```bash
# View all logs
cd /home/deployer/football_base/deploy/ionos
docker compose logs -f

# View API logs only
docker compose logs -f api

# View Caddy logs only
docker compose logs -f caddy

# Restart containers
docker compose restart

# Rebuild containers
docker compose up -d --build

# Check container status
docker compose ps

# Check memory usage
free -h
docker stats
```

### From Your Mac:

```bash
# SSH to VPS
ssh deployer@96.240.7.90

# Test API
curl https://footballbase.duckdns.org/health

# View remote logs
ssh deployer@96.240.7.90 "cd /home/deployer/football_base/deploy/ionos && docker compose logs --tail=50"

# Upload new data file
scp data/newfile.csv deployer@96.240.7.90:/home/deployer/football_base/data/
```

---

## 🐛 Troubleshooting

### Issue: "Connection refused" when testing API

**Check:**
```bash
ssh deployer@96.240.7.90
cd /home/deployer/football_base/deploy/ionos
docker compose ps
docker compose logs caddy
```

**Common causes:**
1. Caddy still getting TLS certificate (wait 1-2 minutes)
2. Firewall blocking ports (check: `sudo ufw status`)
3. DuckDNS not pointing to correct IP (check: `dig +short footballbase.duckdns.org`)

---

### Issue: Out of memory (1GB RAM)

**Add swap space:**
```bash
ssh deployer@96.240.7.90
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
free -h  # Verify swap is active
```

---

### Issue: Frontend shows "DISCONNECTED"

**Check:**
1. Backend is running: `curl https://footballbase.duckdns.org/health`
2. Netlify env var is correct: `NEXT_PUBLIC_WS_URL=wss://footballbase.duckdns.org/ws/chat`
3. Redeploy Netlify site after changing env var

---

### Issue: GitHub Actions deployment fails

**Check:**
1. All 7 GitHub secrets are set correctly
2. SSH key format is correct (full file content, including headers)
3. Deployer user can run docker: `ssh deployer@96.240.7.90 "docker ps"`

---

## 📊 Cost Summary

| Service | Cost |
|---------|------|
| IONOS VPS | €2-4/month |
| DuckDNS | **FREE** |
| Netlify | **FREE** |
| OpenAI API | Usage-based |

**Total: €2-4/month + API usage**

---

## 🎯 Next Steps After Deployment

1. ✅ Monitor uptime with UptimeRobot (free)
2. ✅ Set up automated backups of `/home/deployer/football_base/data`
3. ✅ Consider adding authentication to frontend
4. ✅ Monitor OpenAI API usage in dashboard
5. ✅ If memory becomes an issue, upgrade VPS to 2GB RAM

---

**Questions? Issues?**

Check the full deployment guide: `deploy/ionos/DEPLOY.md`

**Happy deploying! ⚽**
