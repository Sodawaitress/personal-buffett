#!/bin/sh
set -e
mkdir -p /data
python3 -c "from radar_app.data.core import init_db, _migrate; init_db(); _migrate()"
if [ "${SEED_DEMO:-0}" = "1" ]; then
    python3 /app/deploy/seed_demo.py
fi
exec gunicorn -c /app/gunicorn.conf.py run:app
