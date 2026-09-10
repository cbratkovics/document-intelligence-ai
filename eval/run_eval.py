"""Run the sample-corpus evaluation and write a provenance-stamped artifact.

Usage (from the repository root):

    python -m eval.run_eval --embedding none                 # lexical only, no key
    python -m eval.run_eval --embedding hash                 # plumbing check of dense/hybrid
    python -m eval.run_eval --embedding openai --modes lexical,vector,hybrid   # paid
    python -m eval.run_eval --embedding local                # prepared local model

Every run ingests the corpus into a disposable ephemeral index, runs each
requested retrieval mode with identical queries, evaluates against the
document-level qrels, runs the scope/deletion/replacement scenarios, and
writes JSON to ``--out``. Variants that cannot run (no embedding provider)
are recorded as ``not_run`` rather than skipped silently.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.retrieval_metrics import RankedList, compare_runs, evaluate_run, load_qrels  # noqa: E402
from src.core.config import Settings  # noqa: E402
from src.core.types import RetrievalMode  # noqa: E402
from src.rag.generator import Generator  # noqa: E402
from src.rag.reranker import build_reranker  # noqa: E402
from src.rag.retriever import RetrievalRequestError, Retriever  # noqa: E402
from src.rag.service import DocumentService  # noqa: E402


def _git(*args: str) -> Optional[str]:
    try:
        return (
            subprocess.check_output(["git", *args], cwd=ROOT, stderr=subprocess.DEVNULL)
            .decode()
            .strip()
        )
    except Exception:
        return None


def _hash_tree(paths: List[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(str(path.relative_to(ROOT)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _source_hash() -> str:
    return _hash_tree(
        [p for p in (ROOT / "src").rglob("*.py")] + [p for p in (ROOT / "eval").glob("*.py")]
    )


async def _run(args: argparse.Namespace) -> Dict[str, Any]:
    corpus = Path(args.corpus)
    queries = json.loads((corpus / "queries.json").read_text())
    qrels = load_qrels(str(corpus / "qrels.json"))
    scenario = json.loads((corpus / "deletion.json").read_text())
    doc_paths = sorted((corpus / "docs").iterdir())

    settings = Settings(
        storage_mode="ephemeral",
        embedding_provider=args.embedding,
        generation_provider="none",
        reranker_mode=args.reranker,
        data_dir=args.data_dir,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
        app_env="testing",
    )
    service = DocumentService.from_settings(settings)
    retriever = Retriever(service, settings, build_reranker(settings, None))
    Generator(retriever, settings, None)

    started = time.perf_counter()
    name_by_doc: Dict[str, str] = {}
    doc_by_name: Dict[str, str] = {}
    ingest_log = []
    for path in doc_paths:
        result = await service.ingest(path.name, path.read_bytes())
        name_by_doc[result.record.doc_id] = path.name
        doc_by_name[path.name] = result.record.doc_id
        ingest_log.append(
            {"file": path.name, "chunks": result.record.chunk_count, "created": result.created}
        )
    ingest_ms = (time.perf_counter() - started) * 1000

    modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    ks = [int(k) for k in args.ks.split(",")]
    variants: Dict[str, Any] = {}
    reports = {}
    for mode in modes:
        for rerank in [False, True] if args.reranker != "none" else [False]:
            label = f"{mode}{'+rerank' if rerank else ''}"
            run: Dict[str, RankedList] = {}
            per_query: List[Dict[str, Any]] = []
            not_run_reason = None
            for query in queries:
                scope = (
                    [doc_by_name[n] for n in query.get("scope", [])] if query.get("scope") else None
                )
                t0 = time.perf_counter()
                try:
                    result = await retriever.retrieve(
                        query["text"],
                        top_k=args.top_k,
                        mode=RetrievalMode(mode),
                        doc_ids=scope,
                        use_reranker=rerank,
                    )
                except RetrievalRequestError as exc:
                    if exc.status == 409 and mode == "vector":
                        not_run_reason = str(exc)
                        break
                    run[query["id"]] = RankedList(query["id"], [], error=str(exc))
                    per_query.append({"id": query["id"], "error": str(exc)})
                    continue
                if result.mode_effective.value != mode:
                    not_run_reason = (
                        f"requested {mode} but ran {result.mode_effective.value}: "
                        + "; ".join(result.notes)
                    )
                    break
                docs = [name_by_doc[h.doc_id] for h in result.hits]
                run[query["id"]] = RankedList(query["id"], docs)
                supports = query.get("support") or []
                support_found = [any(s in h.text for h in result.hits) for s in supports]
                per_query.append(
                    {
                        "id": query["id"],
                        "kind": query["kind"],
                        "ranked_documents": docs,
                        "chunk_ids": [h.chunk_id for h in result.hits],
                        "support_snippets_found": sum(support_found),
                        "support_snippets_total": len(supports),
                        "rerank_status": result.rerank_status.value,
                        "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
                    }
                )
            if not_run_reason:
                variants[label] = {"status": "not_run", "reason": not_run_reason}
                continue
            report = evaluate_run(run, qrels, ks)
            reports[label] = report
            support_total = sum(q.get("support_snippets_total", 0) for q in per_query)
            support_found_total = sum(q.get("support_snippets_found", 0) for q in per_query)
            variants[label] = {
                "status": "ok",
                "retrieval_mode": mode,
                "reranker": args.reranker if rerank else "none",
                "evaluation": report.to_dict(),
                "support_snippet_recall": {
                    "found": support_found_total,
                    "total": support_total,
                    "note": "fraction of expected support snippets present in the "
                    "top-k retrieved chunks",
                },
                "per_query": per_query,
            }

    comparisons = {}
    if "lexical" in reports:
        for label, report in reports.items():
            if label != "lexical":
                comparisons[f"lexical_vs_{label}"] = {
                    m: compare_runs(reports["lexical"], report, m)
                    for m in (f"ndcg@{max(ks)}", f"recall@{max(ks)}", f"rr@{max(ks)}")
                }

    # Scope / deletion / replacement scenarios (lexical mode; always available)
    checks: List[Dict[str, Any]] = []
    scoped = [q for q in queries if q.get("scope")]
    for query in scoped:
        scope_ids = [doc_by_name[n] for n in query["scope"]]
        result = await retriever.retrieve(
            query["text"], top_k=args.top_k, mode=RetrievalMode.LEXICAL, doc_ids=scope_ids
        )
        leaked = sorted({name_by_doc[h.doc_id] for h in result.hits} - set(query["scope"]))
        checks.append(
            {
                "check": f"scope:{query['id']}",
                "passed": not leaked and bool(result.hits),
                "leaked": leaked,
                "hits": len(result.hits),
            }
        )
    empty = await retriever.retrieve(
        queries[0]["text"], top_k=args.top_k, mode=RetrievalMode.LEXICAL, doc_ids=[]
    )
    checks.append(
        {
            "check": "empty_scope_returns_nothing",
            "passed": len(empty.hits) == 0,
            "hits": len(empty.hits),
        }
    )

    rep = scenario["replace"]
    replaced = await service.ingest(
        rep["file"], rep["new_text"].encode("utf-8"), replace_doc_id=doc_by_name[rep["file"]]
    )
    after = await retriever.retrieve(
        rep["query"], top_k=args.top_k, mode=RetrievalMode.LEXICAL, doc_ids=[replaced.record.doc_id]
    )
    texts = " ".join(h.text for h in after.hits)
    checks.append(
        {
            "check": "replacement_serves_new_version_only",
            "passed": rep["must_contain"] in texts
            and rep["must_not_contain"] not in texts
            and replaced.record.version == 2,
            "version": replaced.record.version,
        }
    )

    deleted_name = scenario["delete"]
    await service.delete_document(doc_by_name[deleted_name])
    after_delete = await retriever.retrieve(
        scenario["query_after_delete"], top_k=args.top_k, mode=RetrievalMode.LEXICAL
    )
    returned = sorted({name_by_doc[h.doc_id] for h in after_delete.hits})
    checks.append(
        {
            "check": "deleted_document_not_retrievable",
            "passed": not (set(returned) & set(scenario["must_not_return"])),
            "returned": returned,
        }
    )
    consistency = service.consistency_report()
    checks.append(
        {
            "check": "indexes_consistent_after_delete",
            "passed": bool(consistency.get("lexical_in_sync"))
            and consistency.get("vectors_in_sync", True),
            "report": consistency,
        }
    )
    service.close()

    return {
        "artifact_version": 1,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "provenance": {
            "git_commit": _git("rev-parse", "HEAD"),
            "git_dirty": bool(_git("status", "--porcelain")),
            "source_hash": _source_hash(),
            "corpus_hash": _hash_tree(doc_paths),
            "queries_hash": hashlib.sha256((corpus / "queries.json").read_bytes()).hexdigest(),
            "qrels_hash": hashlib.sha256((corpus / "qrels.json").read_bytes()).hexdigest(),
            "data_provenance": "original sample documents written for this repository "
            "(see eval/sample_corpus/README.md)",
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "hostname_redacted": True,
        },
        "config": {
            "embedding_provider": settings.resolved_embedding_provider,
            "embedding_identity": service.embedder.identity if service.embedder else None,
            "embedding_semantic": bool(service.embedder and service.embedder.semantic),
            "reranker_mode": settings.reranker_mode,
            "chunking": settings.chunking_config_id,
            "top_k": args.top_k,
            "ks": ks,
            "rrf_k": settings.rrf_k,
            "alpha": 0.5,
            "generation": "none (retrieval evaluation only)",
        },
        "corpus": {
            "documents": ingest_log,
            "queries": len(queries),
            "ingest_ms": round(ingest_ms, 2),
        },
        "variants": variants,
        "comparisons": comparisons,
        "scenario_checks": checks,
        "reproduce": "python -m eval.run_eval " + " ".join(sys.argv[1:]),
        "caveats": [
            "Tiny illustrative corpus: results describe the plumbing, "
            "not general retrieval quality.",
            "hash embeddings carry no semantic signal; dense/hybrid numbers under hash "
            "only prove the pipeline runs.",
            "No statistical significance is claimed.",
        ],
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--corpus", default=str(ROOT / "eval" / "sample_corpus"))
    parser.add_argument(
        "--out",
        default=None,
        help="Artifact path (default: eval/results/<timestamp>-<embedding>.json)",
    )
    parser.add_argument("--embedding", default="none", choices=["none", "hash", "openai", "local"])
    parser.add_argument(
        "--reranker", default="none", choices=["none", "heuristic", "cross_encoder"]
    )
    parser.add_argument("--modes", default="lexical,vector,hybrid")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--ks", default="1,3,5")
    parser.add_argument("--chunk-size", type=int, default=600)
    parser.add_argument("--chunk-overlap", type=int, default=100)
    parser.add_argument("--data-dir", default=os.path.join(".", "data", "eval-tmp"))
    args = parser.parse_args(argv)
    if args.embedding == "openai" and not os.environ.get("OPENAI_API_KEY"):
        print(
            "--embedding openai requires OPENAI_API_KEY (this makes paid API calls)",
            file=sys.stderr,
        )
        return 2
    if args.embedding == "openai":
        print("NOTE: this run makes paid OpenAI embedding calls.", file=sys.stderr)

    artifact = asyncio.run(_run(args))
    out = (
        Path(args.out)
        if args.out
        else ROOT
        / "eval"
        / "results"
        / f"{artifact['timestamp'].replace(':', '')}-{args.embedding}.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(artifact, indent=2, sort_keys=False))

    print(f"artifact: {out}")
    for label, variant in artifact["variants"].items():
        if variant["status"] != "ok":
            print(f"  {label:16s} not_run: {variant['reason']}")
            continue
        means = variant["evaluation"]["summary"]["means"]
        summary = variant["evaluation"]["summary"]
        parts = [
            f"{k}={v['value']:.3f}(n={v['n']})"
            for k, v in means.items()
            if k.startswith(("ndcg@", "recall@", "rr@")) and v["value"] is not None
        ]
        sup = variant["support_snippet_recall"]
        print(
            f"  {label:16s} evaluated={summary['n_evaluated']} "
            f"unanswerable={summary['n_unanswerable']} errors={summary['n_errors']} "
            f"support={sup['found']}/{sup['total']} " + " ".join(parts)
        )
    failed = [c for c in artifact["scenario_checks"] if not c["passed"]]
    passed = len(artifact["scenario_checks"]) - len(failed)
    print(f"  scenario checks: {passed} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
