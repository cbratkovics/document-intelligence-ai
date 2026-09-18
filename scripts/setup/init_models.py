"""Prepare optional local models ahead of time.

The application never downloads models at import, startup, or request time.
Run this script once (network required) to populate the local cache used by
``EMBEDDING_PROVIDER=local`` and ``RERANKER_MODE=cross_encoder``.

    python scripts/setup/init_models.py --embedding
    python scripts/setup/init_models.py --reranker
    python scripts/setup/init_models.py --embedding --reranker --cache-dir ./data/models
    python scripts/setup/init_models.py --fastembed --fastembed-cache-dir ./data/models/fastembed

``--embedding`` and ``--reranker`` require the optional ML dependencies
(pip install -r requirements-ml.txt). ``--cache-dir`` sets ``HF_HOME``, which
the reranker honours; sentence-transformers 2.2.x keeps its own cache under
``SENTENCE_TRANSFORMERS_HOME`` (default ``~/.cache/torch/sentence_transformers``),
so set that variable identically when preparing and when serving.

``--fastembed`` requires ``pip install -r requirements-demo.txt`` and stores the
ONNX model under ``--fastembed-cache-dir`` (or ``FASTEMBED_CACHE_DIR``); point
``FASTEMBED_CACHE_DIR`` at the same directory when serving with
``EMBEDDING_PROVIDER=fastembed``.
"""

from __future__ import annotations

import argparse
import os
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--embedding", action="store_true", help="download the sentence-transformers embedding model")
    parser.add_argument("--reranker", action="store_true", help="download the cross-encoder reranker")
    parser.add_argument("--fastembed", action="store_true", help="download the ONNX embedding model for fastembed")
    parser.add_argument("--fastembed-model", default=os.environ.get("FASTEMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2"))
    parser.add_argument("--fastembed-cache-dir", default=os.environ.get("FASTEMBED_CACHE_DIR"), help="fastembed model cache directory")
    parser.add_argument("--embedding-model", default=os.environ.get("LOCAL_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"))
    parser.add_argument("--reranker-model", default=os.environ.get("CROSS_ENCODER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2"))
    parser.add_argument("--cache-dir", default=os.environ.get("HF_HOME"), help="Hugging Face cache directory (default: HF_HOME or the library default)")
    args = parser.parse_args()
    if not (args.embedding or args.reranker or args.fastembed):
        parser.error("choose --embedding, --reranker and/or --fastembed")
    if args.cache_dir:
        os.environ["HF_HOME"] = args.cache_dir
    os.environ.pop("HF_HUB_OFFLINE", None)
    os.environ.pop("TRANSFORMERS_OFFLINE", None)

    if args.embedding:
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(args.embedding_model, device="cpu")
        print(f"embedding model ready: {args.embedding_model} (dim={model.get_sentence_embedding_dimension()})")
    if args.reranker:
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        AutoTokenizer.from_pretrained(args.reranker_model)
        AutoModelForSequenceClassification.from_pretrained(args.reranker_model)
        print(f"reranker model ready: {args.reranker_model}")
    if args.fastembed:
        from fastembed import TextEmbedding

        kwargs = {"cache_dir": args.fastembed_cache_dir} if args.fastembed_cache_dir else {}
        model = TextEmbedding(args.fastembed_model, **kwargs)
        dim = len(next(iter(model.embed(["probe"]))))
        print(f"fastembed model ready: {args.fastembed_model} (dim={dim})")
    print(
        "Set EMBEDDING_PROVIDER=local|fastembed and/or RERANKER_MODE=cross_encoder to use them."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
