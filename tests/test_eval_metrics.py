"""Hand-checked metric expectations."""

import math

import pytest

from eval.retrieval_metrics import (
    Qrels,
    RankedList,
    average_precision,
    compare_runs,
    dedupe_to_documents,
    evaluate_run,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)

REL = {"a": 2, "b": 1, "c": 0}


def test_precision_recall_rr_conventions():
    ranked = ["x", "a", "a", "b"]  # duplicate 'a' must count once
    assert precision_at_k(ranked, {"a": 2, "b": 1}, 3) == pytest.approx(2 / 3)
    assert precision_at_k(["a"], {"a": 2, "b": 1}, 5) == pytest.approx(1 / 5)  # denominator is k
    assert recall_at_k(ranked, {"a": 2, "b": 1}, 3) == pytest.approx(1.0)
    assert recall_at_k(["a", "a", "a"], {"a": 2, "b": 1}, 3) == pytest.approx(0.5)  # not > 1
    assert recall_at_k(ranked, {}, 3) is None  # unanswerable: undefined, not 0
    assert reciprocal_rank(ranked, {"a": 2}, 10) == pytest.approx(0.5)
    assert reciprocal_rank(ranked, {"b": 1}, 2) == 0.0  # outside cutoff
    assert average_precision(["x", "a", "b"], {"a": 2, "b": 1}) == pytest.approx(
        (1 / 2 + 2 / 3) / 2
    )


def test_ndcg_uses_judgments_and_full_ideal_set():
    graded = {"a": 3, "b": 2, "c": 1}
    # Retrieved b, then an unjudged doc, then a; c missed entirely.
    actual = (2**2 - 1) / math.log2(2) + 0 + (2**3 - 1) / math.log2(4)
    ideal = (2**3 - 1) / math.log2(2) + (2**2 - 1) / math.log2(3) + (2**1 - 1) / math.log2(4)
    assert ndcg_at_k(["b", "z", "a"], graded, 3) == pytest.approx(actual / ideal)
    # Perfect ordering of all judged docs is 1.0; a missed relevant doc keeps it below 1.
    assert ndcg_at_k(["a", "b", "c"], graded, 3) == pytest.approx(1.0)
    assert ndcg_at_k(["a", "b"], graded, 3) < 1.0
    # The old implementation normalised against retrieved scores and would give 1.0 here.
    assert ndcg_at_k(["c", "b", "a"], graded, 3) < 1.0
    assert ndcg_at_k(["a"], {"a": 0}, 3) is None


def test_evaluate_run_aligns_by_query_id_and_reports_everything():
    qrels = Qrels({"q1": {"a": 2, "b": 1}, "q2": {"c": 2}, "q3": {}, "q4": {"d": 1}})
    run = {
        "q2": RankedList("q2", ["c"]),
        "q1": RankedList("q1", ["b", "b", "a"]),
        "q3": RankedList("q3", ["a"]),
        "q4": RankedList("q4", [], error="timeout"),
    }
    report = evaluate_run(run, qrels, ks=[1, 2])
    by_id = {q.query_id: q for q in report.queries}
    assert (
        by_id["q1"].metrics["recall@2"] == pytest.approx(1.0)
        and by_id["q1"].duplicates_removed == 1
    )
    assert by_id["q1"].metrics["precision@1"] == 1.0 and by_id["q1"].metrics["ndcg@1"] < 1.0
    assert by_id["q2"].metrics["precision@1"] == 1.0
    assert by_id["q3"].status == "unanswerable" and by_id["q3"].retrieved_any is True
    assert by_id["q4"].status == "error" and by_id["q4"].error == "timeout"
    s = report.summary
    assert (s["n_queries"], s["n_evaluated"], s["n_unanswerable"], s["n_errors"]) == (4, 2, 1, 1)
    assert s["means"]["recall@2"]["n"] == 2
    missing = evaluate_run({}, qrels, ks=[1])
    assert missing.summary["n_missing"] == 4 and missing.summary["means"] == {}


def test_compare_runs_pairs_by_id_and_zero_baseline_is_undefined():
    qrels = Qrels({"q1": {"a": 1}, "q2": {"b": 1}})
    base = evaluate_run(
        {"q1": RankedList("q1", ["x"]), "q2": RankedList("q2", ["y"])}, qrels, ks=[1]
    )
    better = evaluate_run(
        {"q2": RankedList("q2", ["b"]), "q1": RankedList("q1", ["a"])}, qrels, ks=[1]
    )
    cmp = compare_runs(base, better, "recall@1")
    assert cmp["n_paired"] == 2 and cmp["absolute_delta"] == pytest.approx(1.0)
    assert cmp["relative_delta"] is None  # baseline mean is 0
    assert cmp["wins"] == 2 and cmp["per_query"]["q1"]["delta"] == 1.0
    assert dedupe_to_documents(["a", "b", "a"]).duplicates_removed == 1
