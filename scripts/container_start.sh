#!/bin/sh
set -eu
python manage.py migrate --noinput
# Content transfer/publication is deliberate, never part of web-server startup.
exec gunicorn backend.config.wsgi:application --bind 0.0.0.0:8000 --workers "${WEB_CONCURRENCY:-2}" --timeout 60 --access-logfile - --access-logformat '%(m)s %(s)s %(D)s'
