FROM python:3.12.16-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# SECURITY_REFRESH: CI restores layers from its build cache, so this upgrade step only re-runs
# when its text changes. Bump the date to pull in new security fixes (Trivy, section 6).
ARG SECURITY_REFRESH=2026-11-27
RUN echo "security refresh ${SECURITY_REFRESH}" \
 && apt-get update \
 && apt-get upgrade -y --no-install-recommends \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
# Pinned to the versions the 25 Nov evaluation runs used.
RUN pip install --no-cache-dir httpx==0.28.1 pyyaml==6.0.4 fastembed==0.9.1
ARG EMBED_MODEL=BAAI/bge-small-en-v1.5
ENV EMBED_CACHE_DIR=/models
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('${EMBED_MODEL}', cache_dir='/models')" \
 && chmod -R a+rX /models
ENV HF_HUB_OFFLINE=1
COPY eval /app/eval
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin evaluator
USER 10001
ENTRYPOINT ["python"]
