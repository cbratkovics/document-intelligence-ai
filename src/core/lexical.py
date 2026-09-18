"""BM25 lexical index rebuilt deterministically from the manifest.

The corpus statistics cover every READY chunk in the single shared corpus;
scope restrictions filter *candidates* before ranking, so an empty scope
yields nothing and a document filter never leaks other documents. This is the
supported isolation model (one corpus, optional per-request document scope);
it is not multi-tenant isolation.

Scoring is BM25 (k1=1.5, b=0.75) with the Lucene IDF variant
``log(1 + (N - n + 0.5) / (n + 0.5))``, which stays positive for any corpus
size. (The ``rank_bm25`` package's Okapi variant yields non-positive scores
when a term appears in every document, which makes one-document corpora
unsearchable.) Scores are comparable only within one query.

A short English stopword list is removed from documents and queries alike.
Without it, on a small corpus, function words such as "what" or "does" carry
enough IDF that a question containing no content term still produces lexical
hits, and rank fusion then promotes that noise above genuine dense matches.
"""

from __future__ import annotations

import math
import re
import threading
from collections import Counter
from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence, Tuple

from .types import QueryScope

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)

STOPWORDS = frozenset(
    """
    a an and are as at be been by can could did do does for from had has have he her
    his how i if in into is it its may might of on or our shall she should that the
    their them then there these they this those to us was we were what when where
    which who whom why will with would you your
    """.split()
)


def tokenize(text: str) -> List[str]:
    """Lowercased word tokens with stopwords removed (documents and queries alike)."""
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in STOPWORDS]


@dataclass(frozen=True)
class LexicalEntry:
    chunk_id: str
    doc_id: str
    text: str


@dataclass(frozen=True)
class LexicalHit:
    chunk_id: str
    doc_id: str
    score: float
    rank: int


class BM25:
    def __init__(self, documents: Sequence[Sequence[str]], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.n_docs = len(documents)
        self.doc_freqs: List[Counter] = [Counter(tokens) for tokens in documents]
        self.doc_lengths = [len(tokens) for tokens in documents]
        self.avg_length = (sum(self.doc_lengths) / self.n_docs) if self.n_docs else 0.0
        df: Counter = Counter()
        for freqs in self.doc_freqs:
            df.update(freqs.keys())
        self.idf: Dict[str, float] = {
            term: math.log(1.0 + (self.n_docs - n + 0.5) / (n + 0.5)) for term, n in df.items()
        }

    def scores(self, query_tokens: Sequence[str]) -> List[float]:
        out = [0.0] * self.n_docs
        terms = [t for t in dict.fromkeys(query_tokens) if t in self.idf]
        if not terms:
            return out
        for index, freqs in enumerate(self.doc_freqs):
            length_norm = (
                1.0
                - self.b
                + self.b * (self.doc_lengths[index] / self.avg_length if self.avg_length else 0.0)
            )
            score = 0.0
            for term in terms:
                tf = freqs.get(term, 0)
                if tf:
                    score += self.idf[term] * (tf * (self.k1 + 1.0)) / (tf + self.k1 * length_norm)
            out[index] = score
        return out


class LexicalIndex:
    """In-memory BM25 index. ``rebuild`` is O(corpus); fine for a local demo."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._entries: List[LexicalEntry] = []
        self._bm25: BM25 | None = None
        self.generation: int = -1

    @property
    def size(self) -> int:
        return len(self._entries)

    def rebuild(self, entries: Iterable[LexicalEntry], generation: int) -> None:
        entries = list(entries)
        bm25 = BM25([tokenize(e.text) for e in entries]) if entries else None
        with self._lock:
            self._entries = entries
            self._bm25 = bm25
            self.generation = generation

    def search(
        self,
        query: str,
        n_results: int,
        scope: QueryScope = QueryScope.whole_corpus(),
    ) -> List[LexicalHit]:
        if n_results <= 0 or scope.is_empty:
            return []
        tokens = tokenize(query)
        if not tokens:
            return []
        with self._lock:
            entries = self._entries
            bm25 = self._bm25
        if bm25 is None:
            return []
        scores = bm25.scores(tokens)
        candidates: List[Tuple[float, str, str]] = []
        for entry, score in zip(entries, scores):
            if score <= 0.0 or not scope.allows(entry.doc_id):
                continue
            candidates.append((float(score), entry.chunk_id, entry.doc_id))
        candidates.sort(key=lambda c: (-c[0], c[1]))
        return [
            LexicalHit(chunk_id=cid, doc_id=doc, score=score, rank=i + 1)
            for i, (score, cid, doc) in enumerate(candidates[:n_results])
        ]

    def contains_doc(self, doc_id: str) -> bool:
        with self._lock:
            return any(e.doc_id == doc_id for e in self._entries)
