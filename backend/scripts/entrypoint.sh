#!/bin/sh
# Bring the schema up to date, then start whatever CMD asks for.
set -e

python scripts/migrate.py

exec "$@"
