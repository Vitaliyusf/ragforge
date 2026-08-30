FROM python:3.12-slim

ARG RAGFORGE_GIT_SHA
ARG RAGFORGE_GIT_BRANCH
ARG RAGFORGE_GIT_DIRTY
ARG RAGFORGE_SOURCE_FINGERPRINT_SHA256
ARG RAGFORGE_BUILD_TIMESTAMP
ARG RAGFORGE_IMAGE_TAG

ENV RAGFORGE_GIT_SHA=${RAGFORGE_GIT_SHA} \
    RAGFORGE_GIT_BRANCH=${RAGFORGE_GIT_BRANCH} \
    RAGFORGE_GIT_DIRTY=${RAGFORGE_GIT_DIRTY} \
    RAGFORGE_SOURCE_FINGERPRINT_SHA256=${RAGFORGE_SOURCE_FINGERPRINT_SHA256} \
    RAGFORGE_BUILD_TIMESTAMP=${RAGFORGE_BUILD_TIMESTAMP} \
    RAGFORGE_IMAGE_TAG=${RAGFORGE_IMAGE_TAG}

LABEL org.opencontainers.image.revision=${RAGFORGE_GIT_SHA} \
      org.opencontainers.image.created=${RAGFORGE_BUILD_TIMESTAMP} \
      org.opencontainers.image.ref.name=${RAGFORGE_IMAGE_TAG} \
      io.ragforge.source.dirty=${RAGFORGE_GIT_DIRTY} \
      io.ragforge.source.fingerprint=${RAGFORGE_SOURCE_FINGERPRINT_SHA256}

COPY --from=ghcr.io/astral-sh/uv:0.11.5 /uv /usr/local/bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/opt/hf \
    HF_HUB_DOWNLOAD_TIMEOUT=30

WORKDIR /app

COPY docker/requirements-base.txt /tmp/requirements-base.txt
COPY backend/rag/requirements.txt /tmp/requirements.txt
RUN uv pip install --system --no-cache -r /tmp/requirements-base.txt \
    && uv pip install --system --no-cache torch==2.13.0 --index-url https://download.pytorch.org/whl/cpu \
    && uv pip install --system --no-cache -r /tmp/requirements.txt

RUN groupadd --gid 10001 app \
    && useradd --no-log-init --uid 10001 --gid app --create-home app

# The cache is chowned inside the layer that downloads it. A later `chown -R`
# over /opt/hf rewrites every file into a second layer and duplicates the whole
# ~2.3 GB model cache in the image.
ARG RERANKER_MODEL=BAAI/bge-reranker-v2-m3
ARG RERANKER_MODEL_REVISION=b5160aeac3c6c8fe7beaaaf04c9e0142826b58d1
RUN python -c "from sentence_transformers import CrossEncoder; CrossEncoder('${RERANKER_MODEL}', revision='${RERANKER_MODEL_REVISION}', max_length=512)" \
    && chown -R app:app /opt/hf

ENV RERANKER_MODEL=${RERANKER_MODEL} \
    RERANKER_MODEL_REVISION=${RERANKER_MODEL_REVISION} \
    HF_HUB_OFFLINE=1

COPY --chown=app:app backend/shared /app/shared
COPY --chown=app:app backend/rag /app

RUN chmod +x /app/entrypoint.sh \
    && mkdir -p /app/logs \
    && chown -R app:app /app/logs

USER app:app

EXPOSE 8004

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8004"]
