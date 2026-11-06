"""POST /api/ask. The Ingress sends /api/* here unchanged, so the prefix stays."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from ..schemas import AskRequest, AskResponse
from ..services.answer import answer_with_cache_status

router = APIRouter(prefix="/api")


@router.post("/ask", response_model=AskResponse)
def ask(body: AskRequest, request: Request, response: Response) -> AskResponse:
    state = request.app.state
    result = answer_with_cache_status(
        body.question, state.retriever, state.provider, state.settings, body.history,
        getattr(state, "cache", None), getattr(state, "turns", None),
    )
    # HIT: served from the semantic cache; MISS: looked up, not found; SKIP: follow-up (or no
    # index), so the cache was not consulted. The UI shows this as a chip.
    response.headers["X-Cache"] = result.cache_status
    return result.response
