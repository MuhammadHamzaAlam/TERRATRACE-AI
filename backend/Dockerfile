FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
# rasterio/geopandas/pyproj ship manylinux wheels (GDAL/PROJ bundled); libgl for opencv-headless is not needed.
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.txt .
# CPU-only PyTorch keeps the image small; for GPU use the default PyPI wheels instead (docs/deployment.md)
RUN pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu && pip install -r requirements.txt
COPY backend/ ./backend/
WORKDIR /app/backend
ENV DATABASE_URL=sqlite:////data/terratrace.db STORAGE_DIR=/data/storage MODELS_DIR=/models REPORTS_DIR=/data/reports LEVIR_ROOT=/data/raw/LEVIR-CD
RUN useradd -m app && mkdir -p /data /models && chown -R app /data /models
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD curl -fs http://localhost:8000/api/health || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
