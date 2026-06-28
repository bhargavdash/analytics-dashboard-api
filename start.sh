#!/bin/sh
set -e

DATA_DIR="${DATA_DIR:-/app/db}"

# On first boot against a fresh Railway volume the demo warehouse won't exist.
# Copy the pre-seeded file from the image into the volume so the app can query it.
if [ ! -f "$DATA_DIR/analytics.duckdb" ]; then
    echo "Seeding demo warehouse → $DATA_DIR/analytics.duckdb"
    mkdir -p "$DATA_DIR"
    cp /app/db/analytics.duckdb "$DATA_DIR/analytics.duckdb"
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
