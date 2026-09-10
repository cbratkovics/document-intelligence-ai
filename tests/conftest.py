"""Shared fixtures.

Every test runs with an isolated environment: no ``.env`` file, no provider
keys, temporary data directories, and the deterministic ``hash`` embedding
provider unless a test asks for lexical-only mode. Nothing here mocks modules
at import time.
"""

from __future__ import annotations

import os
import zlib
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import pytest

os.environ["APP_ENV_FILE"] = "/nonexistent/.env"
os.environ["ANONYMIZED_TELEMETRY"] = "False"
for _key in (
    "OPENAI_API_KEY",
    "API_KEY",
    "EMBEDDING_PROVIDER",
    "GENERATION_PROVIDER",
    "STORAGE_MODE",
    "DATA_DIR",
    "RERANKER_MODE",
):
    os.environ.pop(_key, None)

from fastapi.testclient import TestClient  # noqa: E402

from src.api.main import create_app  # noqa: E402
from src.core.config import Settings  # noqa: E402
from src.rag.generator import Generator  # noqa: E402
from src.rag.reranker import build_reranker  # noqa: E402
from src.rag.retriever import Retriever  # noqa: E402
from src.rag.service import DocumentService  # noqa: E402


def make_settings(tmp_path: Path, **overrides: Any) -> Settings:
    base: Dict[str, Any] = dict(
        app_env="testing",
        storage_mode="persistent",
        data_dir=str(tmp_path / "data"),
        embedding_provider="hash",
        generation_provider="none",
        reranker_mode="none",
        chunk_size=200,
        chunk_overlap=40,
        answer_cache_ttl_seconds=300,
        answer_cache_max_entries=64,
    )
    base.update(overrides)
    return Settings(**base)


def make_service(settings: Settings) -> DocumentService:
    return DocumentService.from_settings(settings)


def make_stack(settings: Settings, chat_client=None):
    service = make_service(settings)
    reranker = build_reranker(settings, chat_client)
    retriever = Retriever(service, settings, reranker)
    generator = Generator(retriever, settings, chat_client)
    return service, retriever, generator


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return make_settings(tmp_path)


@pytest.fixture
def service(settings: Settings) -> Iterator[DocumentService]:
    svc = make_service(settings)
    yield svc
    svc.close()


@pytest.fixture
def stack(settings: Settings):
    service, retriever, generator = make_stack(settings)
    yield service, retriever, generator
    service.close()


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


def client_for(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))


# -- sample content ----------------------------------------------------------

REFUND_TEXT = (
    "# Refund policy\n\nCustomers may request a refund within 30 days of delivery. "
    "Approved refunds are issued within 5 business days. Gift cards are not refundable.\n\n"
    "# Contact\n\nReference code REF-2024-07 for refund questions.\n"
)
SHIPPING_TEXT = (
    "Shipping policy. Domestic orders ship within 2 business days. Expedited delivery "
    "takes 1 to 2 business days and costs 18 dollars. Lost parcels are replaced free of charge.\n"
)
SHARED_PARAGRAPH = (
    "The company provides a laptop and one external monitor to every remote employee."
)


def upload(
    client: TestClient,
    name: str,
    text: str,
    metadata: Optional[Dict[str, Any]] = None,
    api_key: Optional[str] = None,
):
    import json

    data = {"metadata": json.dumps(metadata)} if metadata is not None else {}
    headers = {"X-API-Key": api_key} if api_key else {}
    return client.post(
        "/api/v1/documents/upload",
        files={
            "file": (
                name,
                text.encode("utf-8") if isinstance(text, str) else text,
                "application/octet-stream",
            )
        },
        data=data,
        headers=headers,
    )


# -- minimal PDF builder (no external dependency) -------------------------------


def build_pdf(pages: List[str], compress: bool = False) -> bytes:
    """Return a small valid PDF with one line of Helvetica text per page.

    ``pages`` may contain empty strings to produce pages without a text layer.
    """
    objects: List[bytes] = []

    def add(obj: bytes) -> int:
        objects.append(obj)
        return len(objects)

    font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    page_ids: List[int] = []
    pages_id_placeholder = len(objects) + 1 + 2 * len(pages)  # computed below
    content_ids = []
    for text in pages:
        safe = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = f"BT /F1 12 Tf 72 720 Td ({safe}) Tj ET".encode("latin-1") if text else b""
        if compress:
            body = zlib.compress(stream)
            content = (
                b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(body)
                + body
                + b"\nendstream"
            )
        else:
            content = b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"
        content_ids.append(add(content))
    for content_id in content_ids:
        page_ids.append(
            add(
                (
                    f"<< /Type /Page /Parent {pages_id_placeholder} 0 R /MediaBox [0 0 612 792] "
                    f"/Contents {content_id} 0 R /Resources << /Font << /F1 {font} 0 R >> >> >>"
                ).encode()
            )
        )
    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    pages_id = add(f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode())
    assert pages_id == pages_id_placeholder
    catalog = add(f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode())

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{index} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root {catalog} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)
