#!/bin/sh
# Exit immediately if any command exits with a non-zero status
set -e

echo "=== DATABASE MIGRATION ==="
echo "Running Alembic database migrations..."
alembic upgrade head
echo "Database migrations successfully applied."

echo "=== SCHEDULER DAEMON ==="
echo "Starting scheduled daily sync daemon..."
exec python scheduler.py
