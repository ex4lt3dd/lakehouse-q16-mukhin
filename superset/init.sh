#!/bin/sh
set -eu
superset db upgrade
if [ ! -f /app/superset_home/.admin-created ]; then
  superset fab create-admin --username admin --firstname Gleb --lastname Mukhin --email local@example.invalid --password "$SUPERSET_ADMIN_PASSWORD"
  touch /app/superset_home/.admin-created
fi
superset init
exec gunicorn --bind 0.0.0.0:8088 --workers 2 --timeout 120 'superset.app:create_app()'
