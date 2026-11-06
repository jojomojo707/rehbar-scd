"""Turn log (brief section 3.2 step 8 "Store the turn"; design D4, data-models.md).

Every /api/ask outcome (answered, abstained, fallback, cached; follow-ups included) appends
one JSON turn to the Redis list `rahbar:turns`. The list keeps the newest
TURN_LOG_MAX_ENTRIES turns and its TTL is renewed on each append. It is a record only: it is
never read back into a prompt (the browser sends its own history, D4).

A Redis error skips the log with a WARNING; the answer is still returned.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

from ..routes import metrics

log = logging.getLogger("rahbar.turns")

TURNS_KEY = "rahbar:turns"


@dataclass(frozen=True)
class Turn:
    question: str
    answer: str
    request_id: str = ""
    answered_from_context: bool = False
    outcome: str = "answered"          # answered | abstained | fallback | cached
    follow_up: bool = False
    history_turns: int = 0
    ts: float = field(default_factory=time.time)


class TurnLog(Protocol):
    def append(self, turn: Turn) -> None: ...


class NullTurnLog:
    def append(self, turn: Turn) -> None:
        return None


class RedisTurnLog:
    def __init__(self, client: Any, max_entries: int, ttl_seconds: int) -> None:
        self.client = client
        self.max_entries = max(1, int(max_entries))
        self.ttl_seconds = max(1, int(ttl_seconds))

    def append(self, turn: Turn) -> None:
        try:
            pipe = self.client.pipeline(transaction=True)
            pipe.rpush(TURNS_KEY, json.dumps(asdict(turn), ensure_ascii=False))
            pipe.ltrim(TURNS_KEY, -self.max_entries, -1)
            pipe.expire(TURNS_KEY, self.ttl_seconds)
            pipe.execute()
        except Exception as exc:  # noqa: BLE001 - the answer must still be returned
            metrics.DEPENDENCY_ERRORS.labels(dependency="redis").inc()
            log.warning("turn log skipped: redis error",
                        extra={"error_type": type(exc).__name__, "error": str(exc)})
