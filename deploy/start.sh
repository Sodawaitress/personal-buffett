#!/bin/sh
set -e
mkdir -p /data
python3 /app/deploy/seed_demo.py
exec gunicorn run:app --bind "0.0.0.0:${PORT:-8080}" --workers 1 --threads 4 --timeout 180
