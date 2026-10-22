# ==============================================================================
# AMAPP Frontend Multi-Stage Dockerfile (Phase 39)
# Stage 1: Build production static SPA via Vite and Node 22
# Stage 2: Serve via Nginx with reverse proxy to Daphne ASGI backend
# ==============================================================================

# Stage 1: Builder
FROM node:22-alpine AS builder

WORKDIR /app

# Install dependencies using committed lockfile for reproducible builds
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

# Copy frontend source and configuration
COPY frontend/tsconfig.json frontend/tsconfig.app.json frontend/tsconfig.node.json ./
COPY frontend/vite.config.ts frontend/eslint.config.js frontend/index.html ./
COPY frontend/src/ ./src/
COPY frontend/public/ ./public/

# Compile production bundle
RUN npm run build

# Stage 2: Production Nginx Runner
FROM nginx:1.27-alpine AS runner

# Copy custom Nginx reverse proxy configuration
COPY docker/frontend/nginx.conf /etc/nginx/conf.d/default.conf

# Copy compiled static assets from builder
COPY --from=builder /app/dist /usr/share/nginx/html

# Health check
HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
    CMD wget -q -O - http://localhost/healthz || exit 1

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
