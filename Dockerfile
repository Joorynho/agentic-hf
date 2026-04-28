# Runtime image for Agentic HF Mission Control.
#
# The current served dashboard is the static app checked into web/dist.
# The older React/Vite source tree in web/src is not built in this image.
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY web/dist ./web/dist
COPY run.py ./

RUN useradd -m -u 1000 appuser \
    && mkdir -p /app/logs /app/reports /app/data \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

ENV PYTHONUNBUFFERED=1
ENV FASTAPI_HOST=0.0.0.0
ENV FASTAPI_PORT=8000
ENV ENVIRONMENT=production
ENV MISSION_CONTROL_ENABLE_SESSION_CONTROL=false

CMD ["python", "-m", "uvicorn", "src.web.server:app", "--host", "0.0.0.0", "--port", "8000"]
