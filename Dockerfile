# Multi-stage Docker build for Agentic Hedge Fund Platform
# Stage 1: Build React frontend
FROM node:20-alpine AS frontend-builder

WORKDIR /app/web

# Copy package files
COPY web/package.json web/package-lock.json ./

# Install Node dependencies
RUN npm ci

# Copy web source
COPY web/src ./src
COPY web/public ./public
COPY web/tsconfig.json web/tailwind.config.js web/vite.config.ts ./
COPY web/postcss.config.js ./

# Build React
RUN npm run build

# Stage 2: Build Python backend
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy Python requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source
COPY src ./src
COPY pyproject.toml setup.py* ./

# Copy React build from first stage
COPY --from=frontend-builder /app/web/dist ./web/dist

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default environment
ENV PYTHONUNBUFFERED=1
ENV FASTAPI_HOST=0.0.0.0
ENV FASTAPI_PORT=8000

# Start FastAPI server
CMD ["python", "-m", "uvicorn", "src.web.server:app", "--host", "0.0.0.0", "--port", "8000"]
