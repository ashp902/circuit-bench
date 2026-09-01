FROM node:20-bookworm-slim AS frontend-build

WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
ENV NEXT_OUTPUT_MODE=export \
    NEXT_PUBLIC_API_BASE_URL=""
RUN npm run build


FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LAB_ENV=production \
    LAB_DB_PATH=/data/lab.db \
    LAB_FRONTEND_DIR=/app/static \
    LAB_CORS_ORIGINS="" \
    NGSPICE_BIN=/usr/bin/ngspice \
    PORT=8000

RUN apt-get update \
    && apt-get install --yes --no-install-recommends ngspice \
    && rm -rf /var/lib/apt/lists/* \
    && install -d -m 0775 /data

WORKDIR /app
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY --from=frontend-build /build/frontend/out ./static

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8000') + '/health', timeout=3)"

CMD ["python", "-m", "app.production"]
