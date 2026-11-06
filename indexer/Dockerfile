# rahbar-indexer: the Job's image, the only writer to Chroma (section 4.2).
# Build with named build contexts (decision P1), from the repository root:
#   docker build --build-context corpus=corpus --build-context fixtures=eval/fixtures \
#     -t rahbar-indexer:dev indexer
FROM python:3.12.16-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# OCR for scanned pages (corpus property 3): Tesseract and the poppler PDF tools.
# `apt-get upgrade` takes Debian security fixes newer than the base image (Trivy, section 6).
RUN apt-get update \
 && apt-get upgrade -y --no-install-recommends \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng poppler-utils \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt fastembed==0.9.1

# Same pinned model as the api image (section 4.4), baked in at build time.
ARG EMBED_MODEL=BAAI/bge-small-en-v1.5
ENV EMBED_CACHE_DIR=/models
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('${EMBED_MODEL}', cache_dir='/models')" \
 && chmod -R a+rX /models
ENV HF_HUB_OFFLINE=1

# The fetch script and the committed manifest, for the fetch-corpus initContainer (D5),
# and the CI fixture corpus (the ci overlay sets CORPUS_DIR=/app/fixtures).
COPY --from=corpus fetch.py sources.yaml MANIFEST.md /app/corpus/
COPY --from=fixtures *.md /app/fixtures/

COPY pipeline ./pipeline

RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin rahbar
USER 10001

# A Job: runs once and exits. `--dummy` can be passed as an argument.
ENTRYPOINT ["python", "-m", "pipeline.run"]
