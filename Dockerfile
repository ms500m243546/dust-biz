# DustOps AI backend
# Phase B.5: minimal image. DB and frontend service add at later phases.
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install runtime deps first for cache friendliness.
COPY pyproject.toml README.md ./
RUN pip install --upgrade pip && pip install .

# Copy application source.
COPY app ./app

EXPOSE 8000

CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
