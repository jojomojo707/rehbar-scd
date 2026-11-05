"""Liveness and readiness (section 4.3). They answer different questions.

/healthz: is the process alive? It touches nothing, so a slow Chroma never gets a healthy pod
restarted. /readyz: can this pod answer questions right now? Every probe re-runs the checks in
app/services/readiness.py; any failure answers 503 naming it, and Kubernetes takes the pod out
of the Service without restarting it.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

router = APIRouter()


@router.get("/healthz")
def healthz() -> dict[str, str]:
    """Is the process alive? Must never touch Chroma, Redis or the LLM."""
    return {"status": "alive"}


@router.get("/readyz")
def readyz(request: Request, response: Response) -> dict[str, object]:
    result = request.app.state.readiness.check()
    if not result.ready:
        response.status_code = 503
    return result.body
