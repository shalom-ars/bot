# Jonanda Disaster Recovery Plan

## Scenario: Complete VPS Loss
If the primary VPS is deleted, corrupted, or unreachable.

### Prerequisites
You MUST have access to the offsite automated PostgreSQL backups created by `backup_db.sh`.

### Recovery Steps
1. **Provision New VPS**
   - Setup Ubuntu LTS.
   - Install Docker & Docker Compose.
   - Configure Firewalls (deny port 8000, allow 80/443 & SSH).

2. **Restore Code & Configuration**
   - Clone Jonanda repo.
   - Restore `.env` from secure secrets vault (Bitwarden/1Password). **Do not generate a new JWT Secret or user sessions will invalidate.**

3. **Initialize Database Container**
   ```bash
   docker-compose up -d postgres
   ```
   Wait for postgres to be ready (`docker-compose logs -f postgres`).

4. **Restore Database**
   Copy the `.sql.gz` backup to the server.
   Run the restore script:
   ```bash
   # Set environment vars if running outside container, or execute inside:
   export POSTGRES_USER=jonanda
   export POSTGRES_DB=jonanda_db
   ./scripts/restore_db.sh /path/to/backup.sql.gz
   ```

5. **Verify Row Counts & Integrity**
   Execute a query to check total snapshots, users, and the crucial Phase 6 `paper_test_sessions` row.
   ```bash
   docker-compose exec postgres psql -U jonanda -d jonanda_db -c "SELECT count(*) FROM market_snapshots;"
   ```

6. **Start Backend**
   ```bash
   docker-compose up -d backend
   ```

7. **Verify Safety Bounds**
   - Ensure `EXECUTION_MODE=paper` in `.env`.
   - Ensure the RiskManager loaded the restored Drawdown limits.
   - Check `/api/health/detailed` to confirm the daemon resumed Polymarket WebSocket ingestion correctly.
