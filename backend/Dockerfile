FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
RUN groupadd --system app && useradd --system --gid app --create-home app
COPY backend/pyproject.toml ./pyproject.toml
COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./alembic.ini
RUN pip install --upgrade pip && pip install .
COPY backend/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh && chown -R app:app /app
USER app
EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
