# ==============================================================================
# AMAPP Authoritative Simulation Backend Dockerfile (Phase 39)
# Python 3.11 with Daphne ASGI Server (HTTP REST + WebSockets)
# ==============================================================================

FROM python:3.11-slim-bookworm AS runner

# Install essential system utilities for health checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create dedicated non-root user and group
RUN groupadd -g 10001 amapp && \
    useradd -u 10001 -g amapp -s /bin/bash -m amapp

WORKDIR /app

# Install Python runtime dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy backend application source code
COPY backend/ /app/backend/

# Create persistent data and static directories with non-root ownership
RUN mkdir -p /app/data /app/backend/staticfiles && \
    chown -R amapp:amapp /app

# Copy entrypoint script
COPY docker/backend/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh && chown amapp:amapp /app/entrypoint.sh

USER amapp
WORKDIR /app/backend

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DJANGO_SETTINGS_MODULE=config.settings \
    AMAPP_DATA_DIR=/app/data \
    PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://127.0.0.1:8000/api/v1/health/ || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "config.asgi:application"]
