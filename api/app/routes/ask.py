"""POST /api/ask. The Ingress sends /api/* here unchanged, so the prefix stays."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from ..logjson import request_id_var
from ..schemas import AskRequest, AskResponse, RetrieveResponse
from ..services.answer import answer_with_cache_status, retrieve_only

router = APIRouter(prefix="/api")


@router.post("/ask", response_model=AskResponse)
def ask(body: AskRequest, request: Request, response: Response) -> AskResponse:
    state = request.app.state
    result = answer_with_cache_status(
        body.question, state.retriever, state.provider, state.settings, body.history,
        getattr(state, "cache", None), getattr(state, "turns", None),
        bypass_cache="no-cache" in request.headers.get("cache-control", "").lower(),
    )
    # HIT: served from the semantic cache; MISS: looked up, not found; SKIP: follow-up (or no
    # index), so the cache was not consulted; BYPASS: the client sent
    # Cache-Control: no-cache (evaluation runs), so the cache was neither read nor written. The UI shows this as a chip.
    response.headers["X-Cache"] = result.cache_status
    return result.response


@router.post("/retrieve", response_model=RetrieveResponse)
def retrieve(body: AskRequest, request: Request) -> RetrieveResponse:
    """Component-level testing: rank passages for a question without calling the LLM."""
    state = request.app.state
    refs, version = retrieve_only(body.question, state.retriever, state.settings)
    return RetrieveResponse(request_id=request_id_var.get(), collection_version=version,
                            retrieved=refs)
