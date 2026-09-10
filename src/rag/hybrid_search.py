"""Reciprocal rank fusion of dense and lexical candidate lists.

Identity is the chunk ID, never the text: identical passages in different
documents remain distinct. A branch with zero weight contributes nothing (its
candidates are not injected with a zero score). Ties are broken by chunk ID so
results are deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from ..core.lexical import LexicalHit
from ..core.vector_store import VectorHit


@dataclass(frozen=True)
class FusionConfig:
    rrf_k: int = 60
    vector_weight: float = 0.5
    lexical_weight: float = 0.5

    def __post_init__(self) -> None:
        if self.rrf_k <= 0:
            raise ValueError("rrf_k must be positive")
        for w in (self.vector_weight, self.lexical_weight):
            if w < 0.0 or w > 1.0:
                raise ValueError("fusion weights must be within [0, 1]")
        if self.vector_weight == 0.0 and self.lexical_weight == 0.0:
            raise ValueError("at least one fusion weight must be positive")

    @classmethod
    def from_alpha(cls, alpha: float, rrf_k: int = 60) -> "FusionConfig":
        """``alpha`` is the dense weight; the lexical weight is ``1 - alpha``."""
        return cls(rrf_k=rrf_k, vector_weight=alpha, lexical_weight=1.0 - alpha)


@dataclass
class FusedCandidate:
    chunk_id: str
    fusion_score: Optional[float]
    vector_rank: Optional[int] = None
    vector_distance: Optional[float] = None
    lexical_rank: Optional[int] = None
    lexical_score: Optional[float] = None


def reciprocal_rank_fusion(
    vector_hits: Sequence[VectorHit],
    lexical_hits: Sequence[LexicalHit],
    config: FusionConfig,
) -> List[FusedCandidate]:
    """Fuse two ranked lists with RRF: sum(weight / (k + rank))."""
    merged: Dict[str, FusedCandidate] = {}

    if config.vector_weight > 0.0:
        for rank, hit in enumerate(vector_hits, start=1):
            cand = merged.get(hit.chunk_id)
            if cand is None:
                cand = FusedCandidate(chunk_id=hit.chunk_id, fusion_score=0.0)
                merged[hit.chunk_id] = cand
            if cand.vector_rank is None:  # ignore duplicate IDs within a branch
                cand.vector_rank = rank
                cand.vector_distance = hit.distance
                cand.fusion_score = (cand.fusion_score or 0.0) + config.vector_weight / (
                    config.rrf_k + rank
                )

    if config.lexical_weight > 0.0:
        for rank, lhit in enumerate(lexical_hits, start=1):
            cand = merged.get(lhit.chunk_id)
            if cand is None:
                cand = FusedCandidate(chunk_id=lhit.chunk_id, fusion_score=0.0)
                merged[lhit.chunk_id] = cand
            if cand.lexical_rank is None:
                cand.lexical_rank = rank
                cand.lexical_score = lhit.score
                cand.fusion_score = (cand.fusion_score or 0.0) + config.lexical_weight / (
                    config.rrf_k + rank
                )

    ordered = sorted(merged.values(), key=lambda c: (-(c.fusion_score or 0.0), c.chunk_id))
    return ordered
