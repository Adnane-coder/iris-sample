FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements-etl.txt .
RUN pip install --no-cache-dir -r requirements-etl.txt

COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app
COPY data/reference ./data/reference
COPY config ./config

RUN useradd --create-home etl && chown -R etl /app
USER etl

# Default: load every enabled source into iris_staging.
# DATABASE_URL is provided at runtime (never baked into the image).
CMD ["python", "-m", "app.runners.transformer_specs_runner"]
