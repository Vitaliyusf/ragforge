FROM node:24-alpine AS deps

WORKDIR /app

COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund

FROM deps AS builder

ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
ARG NEXT_PUBLIC_RAG_WS_URL=http://localhost:8004
ARG NEXT_PUBLIC_TRAINING_API_BASE_URL=http://localhost:8009/v1/training
ARG NEXT_PUBLIC_VLLM_BASE_URL=http://localhost:8008
ARG NEXT_PUBLIC_ENABLE_TRAINING_TAB=false

ENV NEXT_TELEMETRY_DISABLED=1 \
    NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL} \
    NEXT_PUBLIC_RAG_WS_URL=${NEXT_PUBLIC_RAG_WS_URL} \
    NEXT_PUBLIC_TRAINING_API_BASE_URL=${NEXT_PUBLIC_TRAINING_API_BASE_URL} \
    NEXT_PUBLIC_VLLM_BASE_URL=${NEXT_PUBLIC_VLLM_BASE_URL} \
    NEXT_PUBLIC_ENABLE_TRAINING_TAB=${NEXT_PUBLIC_ENABLE_TRAINING_TAB}

COPY frontend/ ./
RUN npm run build

FROM node:24-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000

COPY --chown=node:node --from=builder /app/.next/standalone ./
COPY --chown=node:node --from=builder /app/.next/static ./.next/static

USER node

EXPOSE 3000

CMD ["node", "server.js"]
