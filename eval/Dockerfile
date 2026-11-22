FROM python:3.12.16-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
RUN pip install --no-cache-dir httpx pyyaml fastembed==0.9.1
ARG EMBED_MODEL=BAAI/bge-small-en-v1.5
ENV EMBED_CACHE_DIR=/models
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('${EMBED_MODEL}', cache_dir='/models')" \
 && chmod -R a+rX /models
ENV HF_HUB_OFFLINE=1
COPY eval /app/eval
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin evaluator
USER 10001
ENTRYPOINT ["python"]
