"""Prometheus request, pipeline, dependency, token, and index metrics."""

from __future__ import annotations

from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

router = APIRouter()

REQUESTS = Counter("rahbar_requests_total", "HTTP requests", ["path", "status"])
LATENCY = Histogram(
    "rahbar_request_seconds",
    "HTTP request latency",
    ["path"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60),
)
RETRIEVAL = Histogram("rahbar_retrieval_seconds", "Retrieval latency")
GENERATION = Histogram("rahbar_generation_seconds", "Generation latency")
EMBEDDING = Histogram("rahbar_embedding_seconds", "Query embedding latency")
CACHE_LOOKUPS = Counter("rahbar_cache_lookups_total", "Semantic cache outcomes", ["result"])
CACHE_HIT_RATIO = Gauge("rahbar_cache_hit_ratio", "Cache hits divided by hits plus misses")
ABSTENTIONS = Counter("rahbar_abstentions_total", "Answers declined", ["reason"])
FALLBACKS = Counter("rahbar_fallbacks_total", "Safe fallback responses", ["reason"])
LLM_TOKENS = Counter("rahbar_llm_tokens_total", "LLM tokens", ["direction"])
LLM_TOKENS_PER_REQUEST = Histogram(
    "rahbar_llm_tokens_per_request", "LLM tokens per request", ["direction"]
)
CITATIONS_DROPPED = Counter("rahbar_citations_dropped_total", "Invalid citations removed")
DEPENDENCY_ERRORS = Counter("rahbar_dependency_errors_total", "Dependency errors", ["dependency"])
INFLIGHT = Gauge("rahbar_inflight_requests", "Requests currently being processed")
TOP1_SIMILARITY = Histogram(
    "rahbar_top1_similarity", "Similarity of the best retrieved passage per query",
    buckets=(0.3, 0.4, 0.5, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0),
)
INJECTIONS_FLAGGED = Counter(
    "rahbar_injections_flagged_total", "Prompt-injection attempts flagged", ["where"]
)
INDEX_INFO = Gauge("rahbar_index_info", "Serving index metadata", ["index_version", "embed_model"])

# Keep all label series visible even before their first matching request.
for _result in ("hit", "miss", "skipped"):
    CACHE_LOOKUPS.labels(result=_result)
for _reason in ("relevance_floor", "model"):
    ABSTENTIONS.labels(reason=_reason)
for _reason in ("provider", "validation", "unknown"):
    FALLBACKS.labels(reason=_reason)
for _where in ("query", "context"):
    INJECTIONS_FLAGGED.labels(where=_where)
for _direction in ("in", "out"):
    LLM_TOKENS.labels(direction=_direction)
    LLM_TOKENS_PER_REQUEST.labels(direction=_direction)
for _dependency in ("chroma", "redis", "groq"):
    DEPENDENCY_ERRORS.labels(dependency=_dependency)


@router.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
