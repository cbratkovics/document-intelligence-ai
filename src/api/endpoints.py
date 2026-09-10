"""HTTP routes for documents, search, question answering, and evaluation."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, Depends, File, Form, HTTPException, Path, Query, UploadFile
from fastapi.responses import StreamingResponse

from ..core.types import IngestionError, NotFoundError, RetrievalMode
from ..rag.generator import Generator
from ..rag.service import DocumentService
from .deps import get_generator, get_service, require_api_key, require_configured_key
from .schemas import (
    DeleteResponse,
    DocumentResponse,
    ErrorResponse,
    JudgeRequest,
    QueryRequest,
    SearchRequest,
    UploadResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_api_key)])

_ERRORS: Dict[Union[int, str], Dict[str, Any]] = {
    400: {"model": ErrorResponse},
    401: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    413: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}

_READ_CHUNK = 64 * 1024


async def _read_upload_bounded(upload: UploadFile, limit: int) -> bytes:
    """Read the upload while enforcing the size limit, not after buffering it all."""
    buffer = bytearray()
    while True:
        piece = await upload.read(_READ_CHUNK)
        if not piece:
            break
        buffer.extend(piece)
        if len(buffer) > limit:
            raise HTTPException(status_code=413, detail=f"File exceeds the {limit} byte limit")
    return bytes(buffer)


def _parse_metadata(raw: Optional[str]) -> Optional[Dict[str, Any]]:
    if raw is None or raw.strip() == "":
        return None
    if len(raw) > 8192:
        raise HTTPException(status_code=400, detail="metadata JSON is too large")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="metadata must be valid JSON")
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="metadata must be a JSON object")
    return parsed


def _upload_response(result) -> UploadResponse:
    return UploadResponse(
        document=DocumentResponse(**result.record.to_public_dict()),
        created=result.created,
        duplicate_of=result.duplicate_of,
        warnings=result.warnings,
        timings_ms={k: round(v, 2) for k, v in result.timings_ms.items()},
    )


# -- documents ---------------------------------------------------------------


@router.post(
    "/documents/upload",
    response_model=UploadResponse,
    tags=["documents"],
    summary="Upload and index a document",
    responses=_ERRORS,
)
async def upload_document(
    file: UploadFile = File(..., description="A .txt, .md, .rst or .pdf file"),
    metadata: Optional[str] = Form(
        None,
        description='Optional flat JSON object of user metadata, e.g. {"team": "finance"}',
    ),
    service: DocumentService = Depends(get_service),
):
    """Ingest synchronously: validate, extract, chunk, embed (if configured), index.

    The response is returned only after every required index write succeeded.
    Re-uploading identical bytes returns the existing document (``created=false``).
    """
    content = await _read_upload_bounded(file, service.settings.max_upload_size)
    result = await service.ingest(file.filename, content, _parse_metadata(metadata))
    return _upload_response(result)


@router.post(
    "/documents/{doc_id}/replace",
    response_model=UploadResponse,
    tags=["documents"],
    summary="Replace a document with a new version",
    responses=_ERRORS,
)
async def replace_document(
    doc_id: str = Path(..., min_length=1, max_length=64),
    file: UploadFile = File(...),
    metadata: Optional[str] = Form(None),
    service: DocumentService = Depends(get_service),
):
    """Index a new version; the previous version stays searchable until commit."""
    content = await _read_upload_bounded(file, service.settings.max_upload_size)
    result = await service.ingest(
        file.filename, content, _parse_metadata(metadata), replace_doc_id=doc_id
    )
    return _upload_response(result)


@router.get(
    "/documents",
    response_model=List[DocumentResponse],
    tags=["documents"],
    summary="List documents",
)
async def list_documents(service: DocumentService = Depends(get_service)):
    return [DocumentResponse(**d.to_public_dict()) for d in service.list_documents()]


@router.get(
    "/documents/{doc_id}",
    response_model=DocumentResponse,
    tags=["documents"],
    summary="Get document status and details",
    responses=_ERRORS,
)
async def get_document(doc_id: str, service: DocumentService = Depends(get_service)):
    return DocumentResponse(**service.get_document(doc_id).to_public_dict())


@router.get(
    "/documents/{doc_id}/chunks",
    tags=["documents"],
    summary="Inspect a document's chunks in source order",
    responses=_ERRORS,
)
async def get_document_chunks(
    doc_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    service: DocumentService = Depends(get_service),
):
    record = service.get_document(doc_id)
    chunks = service.get_chunks(doc_id, offset=offset, limit=limit)
    return {
        "doc_id": doc_id,
        "version": record.version,
        "chunk_count": record.chunk_count,
        "offset": offset,
        "limit": limit,
        "chunks": [
            {
                "chunk_id": c.chunk_id,
                "ordinal": c.ordinal,
                "text": c.text,
                "location": c.location.to_dict(),
                "text_hash": c.text_hash,
            }
            for c in chunks
        ],
    }


@router.delete(
    "/documents/{doc_id}",
    response_model=DeleteResponse,
    tags=["documents"],
    summary="Delete a document and all of its indexed data",
    responses=_ERRORS,
)
async def delete_document(doc_id: str, service: DocumentService = Depends(get_service)):
    """Removes manifest rows, chunks, vectors, the stored file, and cached answers.

    A second delete of the same ID returns 404. If a required index removal
    fails the response is 500 and the document stays excluded from retrieval
    until a retry succeeds.
    """
    result = await service.delete_document(doc_id)
    return DeleteResponse(
        doc_id=result.doc_id,
        status="deleted",
        removed_chunks=result.removed_chunks,
        removed_vectors=result.removed_vectors,
        file_removed=result.file_removed,
    )


@router.delete(
    "/documents",
    tags=["documents"],
    summary="Delete every document (requires a configured API key)",
    dependencies=[Depends(require_configured_key)],
    responses={403: {"model": ErrorResponse}, **_ERRORS},
)
async def clear_all_documents(service: DocumentService = Depends(get_service)):
    removed = await service.clear_all()
    return {"status": "cleared", "documents_removed": removed}


@router.post(
    "/documents/{doc_id}/summary",
    tags=["documents"],
    summary="Summarize a document from its ordered chunks",
    responses=_ERRORS,
)
async def summarize_document(
    doc_id: str,
    max_chars: int = Query(500, ge=50, le=4000),
    generator: Generator = Depends(get_generator),
):
    """Reads the document's own chunks in order (bounded by the context budget).

    Without a generation provider the response carries ``status=excerpts_only``
    and the leading text of the document instead of a generated summary.
    """
    return (await generator.summarize(doc_id, max_chars)).to_dict()


# -- retrieval -----------------------------------------------------------------


@router.post(
    "/search",
    tags=["search"],
    summary="Search chunks (lexical, vector, or hybrid)",
    responses=_ERRORS,
)
async def search(
    request: SearchRequest,
    generator: Generator = Depends(get_generator),
):
    """Returns ranked chunks with per-stage scores kept separate.

    ``mode_effective`` tells you what actually ran; ``rerank_status`` tells you
    whether reranking was applied, disabled, unavailable, or failed.
    """
    result = await generator.retriever.retrieve(
        request.text,
        top_k=request.top_k,
        mode=RetrievalMode(request.mode),
        doc_ids=request.doc_ids,
        alpha=request.alpha,
        use_reranker=request.use_reranker,
    )
    return {
        "query": request.text,
        "results": [h.to_dict() for h in result.hits],
        "total": len(result.hits),
        **result.to_dict(),
    }


@router.post(
    "/query",
    tags=["query"],
    summary="Ask a question and get a citation-checked answer",
    responses=_ERRORS,
)
async def query(request: QueryRequest, generator: Generator = Depends(get_generator)):
    """See ``status`` in the response: answered, unverified_citations,
    insufficient_evidence, excerpts_only, or provider_error."""
    result = await generator.answer(
        request.text,
        top_k=request.top_k,
        mode=RetrievalMode(request.mode),
        doc_ids=request.doc_ids,
        alpha=request.alpha,
        use_reranker=request.use_reranker,
        generate=request.generate,
    )
    return result.to_dict()


@router.post(
    "/query/stream",
    tags=["query"],
    summary="Ask a question with a structured NDJSON event stream",
    responses=_ERRORS,
    response_class=StreamingResponse,
)
async def query_stream(request: QueryRequest, generator: Generator = Depends(get_generator)):
    """Newline-delimited JSON (``application/x-ndjson``), protocol version 1.

    Events: ``meta`` -> ``sources`` -> zero or more ``delta`` (provisional
    text) -> exactly one terminal ``done`` (with the citation-validated
    ``status``/``answer``) or ``error``. Retrieval and scope validation happen
    before the response starts, so those failures are ordinary HTTP errors.
    """
    events = generator.stream_answer(
        request.text,
        top_k=request.top_k,
        mode=RetrievalMode(request.mode),
        doc_ids=request.doc_ids,
        alpha=request.alpha,
        use_reranker=request.use_reranker,
    )
    first = await events.__anext__()  # surfaces validation errors as HTTP errors

    async def body():
        try:
            yield json.dumps(first) + "\n"
            async for event in events:
                yield json.dumps(event) + "\n"
        finally:
            await events.aclose()

    return StreamingResponse(
        body(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Stream-Protocol": "1"},
    )


@router.post(
    "/evaluate/judge",
    tags=["evaluation"],
    summary="LLM rating of an answer (disclosed, optional)",
    responses=_ERRORS,
)
async def judge_answer(request: JudgeRequest, generator: Generator = Depends(get_generator)):
    """Returns ``status=unavailable`` without a provider and ``parse_failed``
    when the judge output is not a valid score object. Never defaults scores."""
    return await generator.judge_answer(request.question, request.answer, request.context)


@router.get("/system/stats", tags=["health"], summary="Index statistics and consistency")
async def system_stats(service: DocumentService = Depends(get_service)):
    return {"stats": service.stats(), "consistency": service.consistency_report()}


__all__ = ["router", "IngestionError", "NotFoundError"]
