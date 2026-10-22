#!/bin/bash
set -e

# ==============================================================================
# AMAPP Backend Container Entrypoint
# ==============================================================================

# Ensure data directory exists and is writable
if [ -n "$AMAPP_DATA_DIR" ]; then
    mkdir -p "$AMAPP_DATA_DIR"
fi

# Run database migrations if explicitly enabled
if [ "$RUN_MIGRATIONS" = "true" ] || [ "$RUN_MIGRATIONS" = "1" ]; then
    echo "Applying database migrations..."
    python manage.py migrate --noinput
fi

# Execute the main container process (defaults to Daphne ASGI server)
exec "$@"
