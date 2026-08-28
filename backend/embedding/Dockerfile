FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.5 /uv /usr/local/bin/uv

# HF_HOME holds the baked model cache. HF_HUB_DOWNLOAD_TIMEOUT bounds any
# runtime fetch so a stalled CDN connection errors instead of hanging startup.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/opt/hf \
    HF_HUB_DOWNLOAD_TIMEOUT=30

WORKDIR /app

COPY docker/requirements-base.txt /tmp/requirements-base.txt
COPY backend/embedding/requirements.txt /tmp/requirements.txt
RUN uv pip install --system --no-cache -r /tmp/requirements-base.txt \
    && uv pip install --system --no-cache -r /tmp/requirements.txt

# Bake the embedding model into the image. Without this the model is fetched
# from huggingface.co on every container start, which blocks lifespan startup
# for minutes and fails outright when the download stalls. Kept above the app
# COPY so code changes do not invalidate the cached model layer.
ARG EMBEDDING_MODEL=intfloat/multilingual-e5-small
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBEDDING_MODEL}')"

ENV EMBEDDING_MODEL=${EMBEDDING_MODEL}

RUN groupadd --gid 10001 app \
    && useradd --no-log-init --uid 10001 --gid app --create-home app

COPY --chown=app:app backend/shared /app/shared
COPY --chown=app:app backend/embedding /app

RUN chmod +x /app/entrypoint.sh \
    && mkdir -p /app/logs /app/uploads \
    && chown -R app:app /app/logs /app/uploads /opt/hf

USER app:app

EXPOSE 8002

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
