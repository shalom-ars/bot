# Jonanda VPS Deployment Guide

This guide details how to securely deploy the Jonanda/JNDA platform to a production VPS (Virtual Private Server) using Docker, PostgreSQL, and Cloudflare.

**CRITICAL RULE:** Real money trading (`LIVE_TRADING_ENABLED`) MUST remain `false`.

## 1. Server Provisioning
1. Provision a Linux VPS (Ubuntu 22.04 or 24.04 LTS).
2. Minimum requirements: 2 vCPU, 4GB RAM, 50GB NVMe SSD.
3. Secure the server via SSH:
   - Disable password authentication.
   - Use Ed25519 SSH keys.
   - Run `ufw allow OpenSSH` and `ufw enable`.

## 2. Docker & Environment
1. Install Docker and Docker Compose via the official Docker repositories.
2. Clone the repository to `/opt/jonanda`.
3. Copy `.env.production.example` to `.env` and **update all secrets**.
   ```bash
   cp .env.production.example .env
   # Generate a JWT secret
   openssl rand -hex 32
   ```

## 3. Deployment Steps
We use Docker Compose to spin up the isolated environment.

```bash
cd /opt/jonanda/backend
docker-compose up -d --build
```

### Health Verification
Verify the backend is healthy:
```bash
curl -f http://localhost:8000/api/health/detailed
```
Output should indicate `database: connected` and `status: ok`.

## 4. PostgreSQL Migration
Since the bot has been running safely on SQLite (Phase 6), we must migrate the local `bot.db` to the new PostgreSQL container **without losing the Phase 6 Paper Test session**.

1. Copy your local `bot.db` to the VPS (e.g., via `scp` or `rsync` into `/opt/jonanda/backend/data/`).
2. Run the migration script inside the backend container:
```bash
docker-compose exec backend python scripts/migrate_to_postgres.py
```
3. Validate row counts matching the SQLite instance.

## 5. Reverse Proxy (Cloudflare + Nginx/Caddy)
Do NOT expose port 8000 directly. 

1. Point your domain DNS to the VPS via Cloudflare.
2. Ensure Cloudflare is set to "Full (Strict)" SSL.
3. Install Caddy (or Nginx) on the VPS:
```Caddyfile
api.jonanda.com {
    reverse_proxy localhost:8000
}
```
Caddy will automatically handle SSL and forward headers. Cloudflare will act as an edge cache and DDoS layer.

## 6. Logs & Backups
- Logs: `docker-compose logs -f backend`
- Backups: Add `scripts/backup_db.sh` to a cronjob to dump PostgreSQL daily to an S3 bucket or external volume.
```bash
0 2 * * * /opt/jonanda/backend/scripts/backup_db.sh >> /var/log/jonanda_backup.log 2>&1
```

## 7. Status & Updates
To restart the system safely:
```bash
docker-compose down
docker-compose up -d
```
Risk state, drawdown, and Paper PnL will survive due to the persistent volume mapping on `postgres_data`.
