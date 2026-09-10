"""Prepare optional local models ahead of time.

The application never downloads models at import, startup, or request time.
Run this script once (network required) to populate the local cache used by
``EMBEDDING_PROVIDER=local`` and ``RERANKER_MODE=cross_encoder``.

    python scripts/setup/init_models.py --embedding
    python scripts/setup/init_models.py --reranker
    python scripts/setup/init_models.py --embedding --reranker --cache-dir ./data/models

Requires the optional ML dependencies (pip install -r requirements-ml.txt).
"""

from __future__ import annotations

import argparse
import os
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--embedding", action="store_true", help="download the sentence-transformers embedding model")
    parser.add_argument("--reranker", action="store_true", help="download the cross-encoder reranker")
    parser.add_argument("--embedding-model", default=os.environ.get("LOCAL_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"))
    parser.add_argument("--reranker-model", default=os.environ.get("CROSS_ENCODER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2"))
    parser.add_argument("--cache-dir", default=os.environ.get("HF_HOME"), help="Hugging Face cache directory (default: HF_HOME or the library default)")
    args = parser.parse_args()
    if not (args.embedding or args.reranker):
        parser.error("choose --embedding and/or --reranker")
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
    print("Set EMBEDDING_PROVIDER=local and/or RERANKER_MODE=cross_encoder to use them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
