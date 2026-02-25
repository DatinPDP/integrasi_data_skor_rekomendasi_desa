#!/bin/sh
# Runs daily inside the isolated backup container

DB_DIR="/app/desa_db/dbs"
BACKUP_DIR="/app/backups"

echo "[$(date)] Starting daily backup check..."

# Ensure backup directory exists
mkdir -p "$BACKUP_DIR"

# Loop through all duckdb files
for db_file in "$DB_DIR"/*.duckdb; do
  # Skip if directory is empty
  [ -e "$db_file" ] || continue
  
  base_name=$(basename "$db_file")
  
  # Find the most recent backup for this specific file
  last_backup=$(ls -t "$BACKUP_DIR"/"$base_name".*.bak 2>/dev/null | head -n 1)

  # Check if file changed (cmp is fast and checks binary equivalence)
  if [ -z "$last_backup" ] || ! cmp -s "$db_file" "$last_backup"; then
      timestamp=$(date +%Y%m%d_%H%M%S)
      cp "$db_file" "$BACKUP_DIR/${base_name}.${timestamp}.bak"
      echo "[$(date)] ✅ Backed up $base_name to ${base_name}.${timestamp}.bak"
  else
      echo "[$(date)] ⏭️  No changes in $base_name, skipping."
  fi
done
