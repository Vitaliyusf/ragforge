FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.5 /uv /usr/local/bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY docker/requirements-base.txt /tmp/requirements-base.txt
COPY backend/files/requirements.txt /tmp/requirements.txt
RUN uv pip install --system --no-cache -r /tmp/requirements-base.txt \
    && uv pip install --system --no-cache -r /tmp/requirements.txt

RUN groupadd --gid 10001 app \
    && useradd --no-log-init --uid 10001 --gid app --create-home app

COPY --chown=app:app backend/shared /app/shared
COPY --chown=app:app backend/files /app

RUN chmod +x /app/entrypoint.sh \
    && mkdir -p /app/logs /app/uploads \
    && chown -R app:app /app/logs /app/uploads

USER app:app

EXPOSE 8005

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8005"]
