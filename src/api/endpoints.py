from fastapi import APIRouter, UploadFile, File, HTTPException, Query, Body, Path
from fastapi.responses import StreamingResponse
from typing import List, Optional, Dict, Any
import logging
import json
from pydantic import BaseModel, Field

from ..rag.retriever import RAGRetriever
from ..rag.generator import RAGGenerator
from ..core.config import settings
from .examples import (
    query_examples,
    advanced_search_examples,
    upload_examples,
    response_examples,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# Pydantic models for request/response
class QueryRequest(BaseModel):
    """Query request model"""

    text: str = Field(..., min_length=1, description="Query text")
    top_k: Optional[int] = Field(default=5, description="Number of results to return")
    filters: Optional[Dict[str, Any]] = Field(
        default=None, description="Metadata filters"
    )
    stream: Optional[bool] = Field(default=False, description="Stream the response")


class AdvancedSearchRequest(BaseModel):
    """Advanced search request model"""

    text: str = Field(..., min_length=1, description="Search query text")
    top_k: Optional[int] = Field(default=10, description="Number of results to return")
    use_hybrid: Optional[bool] = Field(
        default=True, description="Use hybrid search (vector + keyword)"
    )
    use_reranker: Optional[bool] = Field(
        default=True, description="Use cross-encoder reranking"
    )
    alpha: Optional[float] = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Weight for vector search in hybrid mode",
    )
    filters: Optional[Dict[str, Any]] = Field(
        default=None, description="Metadata filters"
    )


class QueryResponse(BaseModel):
    """Query response model"""

    answer: str
    sources: List[Dict[str, Any]]
    confidence: float
    processing_time: float


class DocumentInfo(BaseModel):
    """Document information model"""

    doc_id: str
    filename: str
    chunks: int
    added_at: str


# Initialize services
retriever = RAGRetriever()
generator = RAGGenerator()


@router.post(
    "/documents/upload",
    response_model=Dict[str, Any],
    tags=["documents"],
    summary="Upload a document",
    responses=response_examples,
)
async def upload_document(
    file: UploadFile = File(..., description="Document file to upload"),
    metadata: Optional[str] = Body(
        None, description="JSON metadata string", examples=upload_examples
    ),
):
    """
    Upload a document for processing and indexing.

    Supported file types:
    - PDF (.pdf)
    - Text (.txt)
    - Markdown (.md)
    - reStructuredText (.rst)

    Maximum file size: 10MB

    The document will be:
    1. Validated for type and size
    2. Chunked into smaller segments
    3. Embedded using OpenAI embeddings
    4. Indexed for vector and keyword search
    """
    try:
        # Validate file size
        content = await file.read()
        if len(content) > settings.max_upload_size:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum size is {settings.max_upload_size} bytes",
            )

        # Validate file type
        file_extension = file.filename.split(".")[-1].lower()
        if f".{file_extension}" not in {".txt", ".pdf", ".md", ".rst"}:
            raise HTTPException(
                status_code=400, detail=f"Unsupported file type: {file_extension}"
            )

        # Parse metadata if provided
        metadata_dict = json.loads(metadata) if metadata else {}

        # Add document
        doc_id = await retriever.add_document(
            filename=file.filename, content=content, metadata=metadata_dict
        )

        # Get document info to include chunks count
        doc_info = retriever.get_document_info(doc_id)
        chunks_created = doc_info.get("chunks", 0) if doc_info else 0

        return {
            "document_id": doc_id,
            "filename": file.filename,
            "status": "processed",
            "message": "Document uploaded and processed successfully",
            "chunks_created": chunks_created,
        }

    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid metadata JSON")
    except HTTPException:
        raise  # Re-raise HTTP exceptions to preserve status codes
    except Exception as e:
        logger.error(f"Error uploading document: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/query",
    response_model=QueryResponse,
    tags=["query"],
    summary="Generate answer using RAG",
    responses=response_examples,
    response_model_exclude_none=True,
)
async def query_documents(request: QueryRequest = Body(..., examples=query_examples)):
    """
    Query documents and generate answers using RAG.

    This endpoint:
    1. Performs semantic search to find relevant documents
    2. Uses advanced search with hybrid mode and reranking
    3. Generates a comprehensive answer using GPT-4
    4. Returns source documents for transparency

    For streaming responses, set `stream=true` in the request.
    """
    try:
        # Generate answer
        result = await generator.generate_answer(
            question=request.text, include_sources=True
        )

        return QueryResponse(
            answer=result["answer"],
            sources=result.get("sources", []),
            confidence=result.get("confidence", 0.0),
            processing_time=result.get("processing_time", 0.0),
        )

    except Exception as e:
        logger.error(f"Error querying documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/query/stream")
async def query_documents_stream(request: QueryRequest):
    """
    Query documents with streaming response

    Returns a streaming response for real-time answer generation
    """
    try:

        async def generate():
            async for token in generator.generate_answer_stream(request.text):
                yield token.encode("utf-8")

        return StreamingResponse(
            generate(),
            media_type="text/plain",
            headers={
                "Cache-Control": "no-cache",
                "X-Content-Type-Options": "nosniff",
            },
        )

    except Exception as e:
        logger.error(f"Error in streaming query: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search")
async def search_documents(request: QueryRequest):
    """
    Search documents without generating answers

    Returns raw search results with relevance scores
    """
    try:
        results = await retriever.search(
            query=request.text, top_k=request.top_k, filters=request.filters
        )

        return {"query": request.text, "results": results, "total": len(results)}

    except Exception as e:
        logger.error(f"Error searching documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/search/advanced",
    tags=["search"],
    summary="Advanced document search",
    description="Perform advanced search with hybrid mode and reranking options",
    responses=response_examples,
)
async def advanced_search(
    request: AdvancedSearchRequest = Body(..., examples=advanced_search_examples)
):
    """
    Advanced search with customizable search strategies.

    Features:
    - **Hybrid Search**: Combines vector embeddings with BM25 keyword search
    - **Cross-Encoder Reranking**: Uses LLM to rerank results for better relevance
    - **Configurable Weights**: Adjust balance between semantic and keyword matching

    Parameters:
    - **use_hybrid**: Enable hybrid search (vector + BM25)
    - **use_reranker**: Enable cross-encoder reranking
    - **alpha**: Weight for vector search (0=keyword only, 1=vector only)
    """
    try:
        results = await retriever.advanced_search(
            query=request.text,
            top_k=request.top_k,
            use_hybrid=request.use_hybrid,
            use_reranker=request.use_reranker,
            alpha=request.alpha,
            filters=request.filters,
        )

        return {
            "query": request.text,
            "results": results,
            "total": len(results),
            "search_config": {
                "hybrid": request.use_hybrid,
                "reranker": request.use_reranker,
                "alpha": request.alpha,
            },
        }

    except Exception as e:
        logger.error(f"Error in advanced search: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/documents", response_model=List[DocumentInfo])
async def list_documents():
    """
    List all documents in the system

    Returns a list of all indexed documents
    """
    try:
        documents = retriever.list_documents()
        return [DocumentInfo(**doc) for doc in documents]

    except Exception as e:
        logger.error(f"Error listing documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/documents/{doc_id}")
async def get_document(doc_id: str):
    """
    Get information about a specific document

    - **doc_id**: Document ID
    """
    try:
        doc_info = retriever.get_document_info(doc_id)
        if not doc_info:
            raise HTTPException(status_code=404, detail="Document not found")

        return {"doc_id": doc_id, **doc_info}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting document: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str):
    """
    Delete a document from the system

    - **doc_id**: Document ID to delete
    """
    try:
        success = retriever.delete_document(doc_id)
        if not success:
            raise HTTPException(status_code=404, detail="Document not found")

        return {"message": "Document deleted successfully", "doc_id": doc_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting document: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/documents/{doc_id}/summary")
async def generate_document_summary(
    doc_id: str,
    max_length: Optional[int] = Query(
        default=500, description="Maximum summary length"
    ),
):
    """
    Generate a summary for a specific document

    - **doc_id**: Document ID
    - **max_length**: Maximum summary length in characters
    """
    try:
        summary = await generator.generate_summary(doc_id, max_length)

        return {"doc_id": doc_id, "summary": summary, "max_length": max_length}

    except Exception as e:
        logger.error(f"Error generating summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/documents")
async def clear_all_documents():
    """
    Clear all documents from the system

    **Warning**: This will delete all indexed documents
    """
    try:
        success = retriever.clear_all_documents()
        if not success:
            raise HTTPException(status_code=500, detail="Failed to clear documents")

        return {"message": "All documents cleared successfully"}

    except Exception as e:
        logger.error(f"Error clearing documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/evaluate")
async def evaluate_answer(
    question: str = Body(...), answer: str = Body(...), context: str = Body(...)
):
    """
    Evaluate the quality of an answer

    - **question**: Original question
    - **answer**: Generated answer
    - **context**: Context used for generation
    """
    try:
        evaluation = await generator.evaluate_answer_quality(
            question=question, answer=answer, context=context
        )

        return evaluation

    except Exception as e:
        logger.error(f"Error evaluating answer: {e}")
        raise HTTPException(status_code=500, detail=str(e))
