FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

ENV TIKTOKEN_CACHE_DIR=/opt/tiktoken-cache
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-jpn tesseract-ocr-chi-sim tesseract-ocr-eng && rm -rf /var/lib/apt/lists/*
WORKDIR /app
RUN groupadd --system app && useradd --system --gid app --create-home app
COPY backend/pyproject.toml ./pyproject.toml
COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./alembic.ini
RUN pip install --upgrade pip && pip install . && python -c "import tiktoken; tiktoken.get_encoding('cl100k_base')" && chmod -R a+rX /opt/tiktoken-cache
COPY backend/entrypoint.sh /entrypoint.sh
RUN mkdir -p /app/uploads && chmod 700 /app/uploads && chmod +x /entrypoint.sh && chown -R app:app /app
USER app
EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
