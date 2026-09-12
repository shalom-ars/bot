#!/bin/bash
# Jonanda Production PostgreSQL Backup Script
set -e

BACKUP_DIR="/var/backups/jonanda/postgres"
DATE=$(date +"%Y%m%d_%H%M%S")
RETENTION_DAYS=14

mkdir -p "$BACKUP_DIR"

if [ -z "$POSTGRES_USER" ] || [ -z "$POSTGRES_DB" ]; then
    echo "ERROR: POSTGRES_USER and POSTGRES_DB must be set."
    exit 1
fi

BACKUP_FILE="$BACKUP_DIR/jonanda_backup_$DATE.sql.gz"

echo "Starting PostgreSQL backup for database: $POSTGRES_DB"
pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc | gzip > "$BACKUP_FILE"

if [ $? -eq 0 ]; then
    echo "Backup completed successfully: $BACKUP_FILE"
    
    # Delete backups older than RETENTION_DAYS
    find "$BACKUP_DIR" -type f -name "*.sql.gz" -mtime +$RETENTION_DAYS -exec rm {} \;
    echo "Cleaned up backups older than $RETENTION_DAYS days."
else
    echo "ERROR: Backup failed."
    rm -f "$BACKUP_FILE"
    exit 1
fi
