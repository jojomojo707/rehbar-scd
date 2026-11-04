# rahbar-api: the FastAPI service. Reads the index, never writes it (section 3).
# Build context: api/   ->   docker build -t rahbar-api:dev api
FROM python:3.12.16-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

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
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-graceful-shutdown", "45"]
