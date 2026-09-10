"""Retrieval metrics with explicit conventions.

Evaluation unit: the *document* (a stable corpus identifier such as the sample
filename). A retriever returns chunks; ``dedupe_to_documents`` keeps the first
occurrence of each document so repeated chunks of one document cannot inflate
recall or count as several hits.

Conventions (state them when you compare numbers across systems):
- precision@k divides by k, even when fewer than k results were returned.
- recall@k divides by the number of judged-relevant documents. Queries with no
  relevant document are *unanswerable*; their recall/AP/RR are ``None`` and
  they are summarized separately (``abstention``), never as 0/0.
- MRR uses the first relevant document within the cutoff ``k``; 0 if none.
- nDCG uses gain ``2**rel - 1`` and discount ``log2(rank + 1)``. Gains come
  from the independent relevance judgments (qrels), never from retrieval
  scores. The ideal DCG is computed from the *full* judged set, including
  relevant documents the retriever missed. Unjudged documents have gain 0.
- Comparisons align by query id, never by list position. A relative change
  from a zero baseline is undefined and reported as ``None``.
"""

from __future__ import annotations

import json
import math
import statistics
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence


@dataclass(frozen=True)
class Qrels:
    """Graded judgments: ``judgments[query_id][doc_id] = grade`` (grade >= 1 is relevant)."""

    judgments: Mapping[str, Mapping[str, int]]

    def relevant(self, query_id: str) -> Dict[str, int]:
        return {d: int(g) for d, g in self.judgments.get(query_id, {}).items() if int(g) > 0}

    @classmethod
    def from_dict(cls, data: Mapping[str, Mapping[str, int]]) -> "Qrels":
        return cls({q: dict(v) for q, v in data.items()})


@dataclass
class RankedList:
    query_id: str
    doc_ids: List[str]
    error: Optional[str] = None
    duplicates_removed: int = 0


def dedupe_to_documents(doc_ids_in_rank_order: Iterable[str]) -> RankedList:
    seen: List[str] = []
    dupes = 0
    for doc_id in doc_ids_in_rank_order:
        if doc_id in seen:
            dupes += 1
            continue
        seen.append(doc_id)
    return RankedList(query_id="", doc_ids=seen, duplicates_removed=dupes)


# -- per-query metrics ----------------------------------------------------------


def precision_at_k(ranked: Sequence[str], relevant: Mapping[str, int], k: int) -> float:
    if k <= 0:
        raise ValueError("k must be positive")
    top = list(dict.fromkeys(ranked))[:k]
    return sum(1 for d in top if d in relevant) / k


def recall_at_k(ranked: Sequence[str], relevant: Mapping[str, int], k: int) -> Optional[float]:
    if k <= 0:
        raise ValueError("k must be positive")
    if not relevant:
        return None
    top = list(dict.fromkeys(ranked))[:k]
    return sum(1 for d in top if d in relevant) / len(relevant)


def reciprocal_rank(ranked: Sequence[str], relevant: Mapping[str, int], k: int) -> Optional[float]:
    if not relevant:
        return None
    for rank, doc in enumerate(list(dict.fromkeys(ranked))[:k], start=1):
        if doc in relevant:
            return 1.0 / rank
    return 0.0


def average_precision(
    ranked: Sequence[str], relevant: Mapping[str, int], k: Optional[int] = None
) -> Optional[float]:
    if not relevant:
        return None
    unique = list(dict.fromkeys(ranked))
    if k is not None:
        unique = unique[:k]
    hits = 0
    total = 0.0
    for rank, doc in enumerate(unique, start=1):
        if doc in relevant:
            hits += 1
            total += hits / rank
    return total / len(relevant)


def dcg(gains: Sequence[float]) -> float:
    return sum((2.0**g - 1.0) / math.log2(i + 1) for i, g in enumerate(gains, start=1))


def ndcg_at_k(ranked: Sequence[str], graded: Mapping[str, int], k: int) -> Optional[float]:
    """nDCG@k from judgments; ideal ranking uses every judged-relevant document."""
    if k <= 0:
        raise ValueError("k must be positive")
    relevant = {d: int(g) for d, g in graded.items() if int(g) > 0}
    if not relevant:
        return None
    unique = list(dict.fromkeys(ranked))[:k]
    actual = dcg([float(relevant.get(d, 0)) for d in unique])
    ideal = dcg(sorted((float(g) for g in relevant.values()), reverse=True)[:k])
    return actual / ideal if ideal > 0 else None


def hit_at_k(ranked: Sequence[str], relevant: Mapping[str, int], k: int) -> Optional[float]:
    if not relevant:
        return None
    return 1.0 if any(d in relevant for d in list(dict.fromkeys(ranked))[:k]) else 0.0


# -- run-level evaluation --------------------------------------------------------


@dataclass
class QueryReport:
    query_id: str
    status: str  # evaluated | unanswerable | error | missing
    num_retrieved: int
    num_relevant: int
    duplicates_removed: int
    retrieved: List[str]
    relevant: List[str]
    metrics: Dict[str, Optional[float]] = field(default_factory=dict)
    retrieved_any: Optional[bool] = None  # for unanswerable queries: did we return anything?
    error: Optional[str] = None


@dataclass
class RunReport:
    ks: List[int]
    queries: List[QueryReport]
    summary: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ks": self.ks,
            "queries": [asdict(q) for q in self.queries],
            "summary": self.summary,
        }


def evaluate_run(
    run: Mapping[str, RankedList], qrels: Qrels, ks: Sequence[int] = (1, 3, 5, 10)
) -> RunReport:
    """Evaluate ``run`` against ``qrels``. Every judged query is reported, including
    missing and failed ones; summary means state their denominators."""
    ks = sorted(set(int(k) for k in ks))
    reports: List[QueryReport] = []
    for query_id in sorted(qrels.judgments):
        relevant = qrels.relevant(query_id)
        ranked = run.get(query_id)
        if ranked is None:
            reports.append(
                QueryReport(
                    query_id,
                    "missing",
                    0,
                    len(relevant),
                    0,
                    [],
                    sorted(relevant),
                    error="no result for query",
                )
            )
            continue
        if ranked.error:
            reports.append(
                QueryReport(
                    query_id, "error", 0, len(relevant), 0, [], sorted(relevant), error=ranked.error
                )
            )
            continue
        docs = list(dict.fromkeys(ranked.doc_ids))
        dupes = ranked.duplicates_removed + (len(ranked.doc_ids) - len(docs))
        if not relevant:
            reports.append(
                QueryReport(
                    query_id,
                    "unanswerable",
                    len(docs),
                    0,
                    dupes,
                    docs,
                    [],
                    retrieved_any=bool(docs),
                )
            )
            continue
        metrics: Dict[str, Optional[float]] = {}
        for k in ks:
            metrics[f"precision@{k}"] = precision_at_k(docs, relevant, k)
            metrics[f"recall@{k}"] = recall_at_k(docs, relevant, k)
            metrics[f"ndcg@{k}"] = ndcg_at_k(docs, qrels.judgments[query_id], k)
            metrics[f"hit@{k}"] = hit_at_k(docs, relevant, k)
        metrics[f"rr@{max(ks)}"] = reciprocal_rank(docs, relevant, max(ks))
        metrics["ap"] = average_precision(docs, relevant)
        reports.append(
            QueryReport(
                query_id,
                "evaluated",
                len(docs),
                len(relevant),
                dupes,
                docs,
                sorted(relevant),
                metrics,
            )
        )

    evaluated = [r for r in reports if r.status == "evaluated"]
    unanswerable = [r for r in reports if r.status == "unanswerable"]
    summary: Dict[str, Any] = {
        "n_queries": len(reports),
        "n_evaluated": len(evaluated),
        "n_unanswerable": len(unanswerable),
        "n_errors": sum(1 for r in reports if r.status == "error"),
        "n_missing": sum(1 for r in reports if r.status == "missing"),
        "means": {},
        "abstention": {
            "n": len(unanswerable),
            "returned_results_for": sum(1 for r in unanswerable if r.retrieved_any),
            "note": "retrieval always returns candidates; abstention is decided at answer time",
        },
        "conventions": "see eval/retrieval_metrics.py docstring",
    }
    if evaluated:
        names = list(evaluated[0].metrics)
        for name in names:
            values = [r.metrics[name] for r in evaluated if r.metrics.get(name) is not None]
            summary["means"][name] = {
                "value": (sum(values) / len(values)) if values else None,
                "n": len(values),
            }
    return RunReport(ks, reports, summary)


def compare_runs(baseline: RunReport, candidate: RunReport, metric: str) -> Dict[str, Any]:
    """Paired comparison aligned by query id. Small suites give noisy deltas."""
    base = {q.query_id: q for q in baseline.queries if q.status == "evaluated"}
    cand = {q.query_id: q for q in candidate.queries if q.status == "evaluated"}
    shared = sorted(set(base) & set(cand))
    diffs: List[float] = []
    per_query: Dict[str, Dict[str, Optional[float]]] = {}
    for qid in shared:
        b = base[qid].metrics.get(metric)
        c = cand[qid].metrics.get(metric)
        if b is None or c is None:
            continue
        diffs.append(c - b)
        per_query[qid] = {"baseline": b, "candidate": c, "delta": c - b}
    mean_base = statistics.fmean([v["baseline"] for v in per_query.values()]) if per_query else None
    mean_cand = (
        statistics.fmean([v["candidate"] for v in per_query.values()]) if per_query else None
    )
    absolute = (mean_cand - mean_base) if per_query else None
    relative = None
    if absolute is not None and mean_base not in (None, 0.0):
        relative = absolute / mean_base
    return {
        "metric": metric,
        "n_paired": len(diffs),
        "n_unpaired": len(set(base) ^ set(cand)),
        "baseline_mean": mean_base,
        "candidate_mean": mean_cand,
        "absolute_delta": absolute,
        "relative_delta": relative,  # None when the baseline mean is 0 (undefined)
        "wins": sum(1 for d in diffs if d > 0),
        "losses": sum(1 for d in diffs if d < 0),
        "ties": sum(1 for d in diffs if d == 0),
        "per_query": per_query,
        "note": "paired by query id; no significance claim is made for small suites",
    }


def load_qrels(path: str) -> Qrels:
    with open(path, "r", encoding="utf-8") as handle:
        return Qrels.from_dict(json.load(handle))
