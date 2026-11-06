# rahbar-api: the FastAPI service. Reads the index, never writes it (section 3).
# Build context: api/   ->   docker build -t rahbar-api:dev api
FROM python:3.12.16-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Debian security fixes newer than the base image (Trivy, section 6: e.g. apt CVE-2026-109518).
RUN apt-get update \
 && apt-get upgrade -y --no-install-recommends \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first, so a code change does not reinstall them.
# fastembed runs the pinned embedding model on CPU (decision D7).
COPY requirements.txt .
RUN pip install -r requirements.txt fastembed==0.9.1

# The embedding model is downloaded at BUILD time into /models, so a pod never
# downloads anything at runtime (HF_HUB_OFFLINE=1). Must equal EMBED_MODEL in the ConfigMap.
ARG EMBED_MODEL=BAAI/bge-small-en-v1.5
ENV EMBED_CACHE_DIR=/models
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('${EMBED_MODEL}', cache_dir='/models')" \
 && chmod -R a+rX /models
ENV HF_HUB_OFFLINE=1

COPY app ./app

# Non-root user (section 4.7). The pod spec also sets runAsNonRoot and a read-only root.
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin rahbar
USER 10001

EXPOSE 8000
# Exec form, so SIGTERM reaches uvicorn (PID 1). 45 s lets in-flight answers finish;
# see docs/architecture/deployment.md § Rollout settings.
# Keep-alive 75 s: ingress-nginx reuses upstream connections for 60 s. With uvicorn's default
# of 5 s, uvicorn could close a connection just as nginx sent a request on it, and the user got
# a 502 ("connection reset by peer"); seen twice in 1,172 requests under load on 6 Nov.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--timeout-graceful-shutdown", "45", "--timeout-keep-alive", "75"]
