#!/bin/bash
# Jonanda Production PostgreSQL Restore Script
set -e

if [ -z "$1" ]; then
    echo "Usage: ./restore_db.sh <path_to_backup_file.sql.gz>"
    exit 1
fi

BACKUP_FILE=$1

if [ ! -f "$BACKUP_FILE" ]; then
    echo "ERROR: Backup file $BACKUP_FILE not found."
    exit 1
fi

if [ -z "$POSTGRES_USER" ] || [ -z "$POSTGRES_DB" ]; then
    echo "ERROR: POSTGRES_USER and POSTGRES_DB must be set."
    exit 1
fi

echo "WARNING: This will overwrite the database '$POSTGRES_DB'."
read -p "Are you sure you want to proceed? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Restore aborted."
    exit 1
fi

echo "Restoring PostgreSQL database: $POSTGRES_DB from $BACKUP_FILE"

# Drop and recreate db to ensure clean restore, or just restore into existing.
# pg_restore handles data. We will use zcat into psql if it was plain sql, but we used pg_dump -Fc.
# Since we gzip'd a custom format dump... wait. pg_dump -Fc produces a custom binary format, which shouldn't be gzip'd manually or it needs to be unzipped first.
# Unzip to a tmp file
TMP_DUMP="/tmp/restore_dump_$$.dump"
zcat "$BACKUP_FILE" > "$TMP_DUMP"

pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists "$TMP_DUMP"

rm "$TMP_DUMP"
echo "Restore completed successfully."
