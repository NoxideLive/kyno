# syntax=docker/dockerfile:1
# Phi gateway: shared pip layer; use --target dev (Compose) or --target prod.
FROM pytorch/pytorch:2.4.1-cuda12.4-cudnn9-runtime AS phi-base

WORKDIR /app/services/phi-gateway

RUN apt-get update \
    && apt-get install -y --no-install-recommends poppler-utils curl \
    && rm -rf /var/lib/apt/lists/*

COPY services/phi-gateway/requirements.txt services/phi-gateway/requirements-phi.txt ./
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements-phi.txt

ENV KYNO_REPO_ROOT=/app \
    PYTHONUNBUFFERED=1 \
    NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility

FROM phi-base AS dev

COPY services/phi-gateway/docker-entrypoint.dev.sh ./docker-entrypoint.dev.sh
RUN chmod +x docker-entrypoint.dev.sh

EXPOSE 8090

ENTRYPOINT ["./docker-entrypoint.dev.sh"]

FROM phi-base AS prod

COPY services/phi-gateway/ ./
RUN chmod +x docker-entrypoint.sh

ENV PHI_MAX_SEQ_LENGTH=2048 \
    DOMAIN_CONFIDENCE_THRESHOLD=0.4

EXPOSE 8090

ENTRYPOINT ["./docker-entrypoint.sh"]
