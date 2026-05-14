#!/bin/bash
set -e

# Reset DB stack before start (same as cleanup): removes containers + postgres_data volume.
# Matches a "clean slate on every localserver run" even if the last session exited uncleanly.
echo "Resetting database (docker compose down -v)..."
uv run poe services-down-v
uv run poe services-up

CLEANUP_DONE=0
cleanup() {
    if [[ "${CLEANUP_DONE}" -eq 1 ]]; then
        return 0
    fi
    CLEANUP_DONE=1
    trap - INT TERM EXIT
    echo "Stopping database and removing volume (docker compose down -v)..."
    uv run poe services-down-v || true
}

trap cleanup INT TERM EXIT

uv run alembic upgrade head

# Run local server; when it exits (Ctrl+C, SIGTERM, crash, normal), EXIT runs cleanup.
uv run poe runserver
