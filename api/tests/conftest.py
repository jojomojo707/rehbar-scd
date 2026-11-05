"""Shared test set-up. Tests never use the network (section 6): Chroma and Redis point at a
closed local port, so the api's start-up readiness check fails instantly instead of waiting
on DNS for the cluster names `chroma` and `redis`."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def no_cluster_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    for host, port in (("CHROMA_HOST", "CHROMA_PORT"), ("REDIS_HOST", "REDIS_PORT")):
        monkeypatch.setenv(host, "127.0.0.1")
        monkeypatch.setenv(port, "1")
