"""Reciprocal-rank fusion for dense and exact-term Chroma result lists."""

from __future__ import annotations

from ..schemas import Passage


def reciprocal_rank_fusion(
    rankings: list[list[Passage]], top_k: int, rank_constant: int = 60
) -> list[Passage]:
    """Combine ranked lists by chunk id while preserving each passage's dense score."""
    fused: dict[str, tuple[float, Passage]] = {}
    for ranking in rankings:
        for rank, passage in enumerate(ranking, start=1):
            contribution = 1.0 / (rank_constant + rank)
            previous = fused.get(passage.chunk_id)
            if previous is None:
                fused[passage.chunk_id] = (contribution, passage)
            else:
                best_passage = passage if passage.score > previous[1].score else previous[1]
                fused[passage.chunk_id] = (previous[0] + contribution, best_passage)

    ordered = sorted(
        fused.values(),
        key=lambda item: (-item[0], -item[1].score, item[1].chunk_id),
    )
    return [passage for _, passage in ordered[:top_k]]
