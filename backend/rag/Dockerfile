FROM python:3.11-slim

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
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY docker/requirements-base.txt /tmp/requirements-base.txt
COPY backend/rag/requirements.txt /tmp/requirements.txt
RUN uv pip install --system --no-cache -r /tmp/requirements-base.txt \
    && uv pip install --system --no-cache -r /tmp/requirements.txt

COPY backend/shared /app/shared
COPY backend/rag /app

RUN chmod +x /app/entrypoint.sh 2>/dev/null || true

EXPOSE 8004

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8004"]
