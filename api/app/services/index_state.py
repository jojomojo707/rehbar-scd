"""Read the blue/green active-index pointer and cache its status briefly."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from ..config import Settings


@dataclass(frozen=True)
class IndexStatus:
    active: str | None
    previous: str | None
    metadata: dict[str, Any] = field(default_factory=dict)
    checks: dict[str, str] = field(default_factory=dict)
    details: dict[str, str] = field(default_factory=dict)
    failed: str | None = None

    @property
    def ready(self) -> bool:
        return self.failed is None and all(value == "ok" for value in self.checks.values())


class IndexState:
    """Resolve the active collection. A cache invalidator can be wired in later."""

    def __init__(
        self,
        settings: Settings,
        client: Any | None = None,
        cache_invalidator: Callable[[str], int] | None = None,
    ) -> None:
        self.settings = settings
        if client is None:
            import chromadb
            from chromadb.config import Settings as ChromaSettings

            client = chromadb.HttpClient(
                host=settings.chroma_host,
                port=settings.chroma_port,
                settings=ChromaSettings(anonymized_telemetry=False),
            )
        self.client = client
        self.cache_invalidator = cache_invalidator
        self._cached: IndexStatus | None = None
        self._refreshed_at = 0.0

    def current(self) -> IndexStatus:
        ttl = max(0, int(self.settings.index_refresh_seconds))
        if self._cached is not None and time.monotonic() - self._refreshed_at < ttl:
            return self._cached
        return self.refresh()

    def refresh(self) -> IndexStatus:
        checks = {"chroma": "error", "index_pointer": "error", "collection": "error"}
        details: dict[str, str] = {}
        active: str | None = None
        previous: str | None = None
        metadata: dict[str, Any] = {}
        try:
            self.client.heartbeat()
            checks["chroma"] = "ok"
        except Exception as exc:
            details["chroma"] = str(exc)

        pointer_name = f"{self.settings.collection}-active"
        try:
            pointer = self.client.get_collection(name=pointer_name, embedding_function=None)
            pointer_metadata = dict(pointer.metadata or {})
            active = str(pointer_metadata.get("active") or "") or None
            previous = str(pointer_metadata.get("previous") or "") or None
            if active:
                checks["index_pointer"] = "ok"
            else:
                checks["index_pointer"] = "missing_active"
                details["index_pointer"] = f"{pointer_name} does not name an active collection"
        except Exception as exc:
            checks["index_pointer"] = "missing"
            details["index_pointer"] = str(exc)

        if active:
            try:
                collection = self.client.get_collection(name=active, embedding_function=None)
                metadata = dict(collection.metadata or {})
                count = int(collection.count())
                if metadata.get("status") == "complete" and count > 0:
                    checks["collection"] = "ok"
                elif count == 0:
                    checks["collection"] = "empty"
                    details["collection"] = f"active collection {active} contains no records"
                else:
                    checks["collection"] = "incomplete"
                    details["collection"] = f"active collection {active} is not marked complete"
            except Exception as exc:
                checks["collection"] = "missing"
                details["collection"] = str(exc)
        else:
            checks["collection"] = "skipped"

        failed = next((name for name, value in checks.items() if value != "ok"), None)
        status = IndexStatus(active, previous, metadata, checks, details, failed)
        prior_active = self._cached.active if self._cached else None
        if active and prior_active and active != prior_active and self.cache_invalidator:
            self.cache_invalidator(active)
        self._cached = status
        self._refreshed_at = time.monotonic()
        return status
