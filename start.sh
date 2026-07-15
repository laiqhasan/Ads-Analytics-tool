#!/bin/sh
# Exit immediately if any command exits with a non-zero status
set -e

echo "=== DATABASE MIGRATION ==="
echo "Running Alembic database migrations..."
alembic upgrade head
echo "Database migrations successfully applied."

echo "=== STREAMLIT WEB APP ==="
echo "Starting Streamlit dashboard on port $PORT..."
exec streamlit run app.py --server.port $PORT --server.address 0.0.0.0
