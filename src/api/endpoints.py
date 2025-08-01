from fastapi import APIRouter, UploadFile, File, HTTPException, Query, Body
from fastapi.responses import StreamingResponse
from typing import List, Optional, Dict, Any
import logging
import json
from pydantic import BaseModel, Field

from ..rag.retriever import RAGRetriever
from ..rag.generator import RAGGenerator
from ..core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


# Pydantic models for request/response
class QueryRequest(BaseModel):
    """Query request model"""
    text: str = Field(..., description="Query text")
    top_k: Optional[int] = Field(default=5, description="Number of results to return")
    filters: Optional[Dict[str, Any]] = Field(default=None, description="Metadata filters")
    stream: Optional[bool] = Field(default=False, description="Stream the response")


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


@router.post("/documents/upload", response_model=Dict[str, str])
async def upload_document(
    file: UploadFile = File(...),
    metadata: Optional[str] = None
):
    """
    Upload a document for processing
    
    - **file**: Document file (PDF, TXT, MD, RST)
    - **metadata**: Optional JSON metadata string
    """
    try:
        # Validate file size
        content = await file.read()
        if len(content) > settings.max_upload_size:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum size is {settings.max_upload_size} bytes"
            )
        
        # Validate file type
        file_extension = file.filename.split('.')[-1].lower()
        if f".{file_extension}" not in {'.txt', '.pdf', '.md', '.rst'}:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {file_extension}"
            )
        
        # Parse metadata if provided
        metadata_dict = json.loads(metadata) if metadata else {}
        
        # Add document
        doc_id = await retriever.add_document(
            filename=file.filename,
            content=content,
            metadata=metadata_dict
        )
        
        return {
            "document_id": doc_id,
            "filename": file.filename,
            "status": "processed",
            "message": "Document uploaded and processed successfully"
        }
        
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid metadata JSON")
    except Exception as e:
        logger.error(f"Error uploading document: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/query", response_model=QueryResponse)
async def query_documents(request: QueryRequest):
    """
    Query documents and get AI-generated answers
    
    Returns answers based on the document context
    """
    try:
        # Generate answer
        result = await generator.generate_answer(
            question=request.text,
            include_sources=True
        )
        
        return QueryResponse(
            answer=result['answer'],
            sources=result.get('sources', []),
            confidence=result.get('confidence', 0.0),
            processing_time=result.get('processing_time', 0.0)
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
                yield token.encode('utf-8')
        
        return StreamingResponse(
            generate(),
            media_type="text/plain",
            headers={
                "Cache-Control": "no-cache",
                "X-Content-Type-Options": "nosniff",
            }
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
            query=request.text,
            top_k=request.top_k,
            filters=request.filters
        )
        
        return {
            "query": request.text,
            "results": results,
            "total": len(results)
        }
        
    except Exception as e:
        logger.error(f"Error searching documents: {e}")
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
        
        return {
            "doc_id": doc_id,
            **doc_info
        }
        
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
        
        return {
            "message": "Document deleted successfully",
            "doc_id": doc_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting document: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/documents/{doc_id}/summary")
async def generate_document_summary(
    doc_id: str,
    max_length: Optional[int] = Query(default=500, description="Maximum summary length")
):
    """
    Generate a summary for a specific document
    
    - **doc_id**: Document ID
    - **max_length**: Maximum summary length in characters
    """
    try:
        summary = await generator.generate_summary(doc_id, max_length)
        
        return {
            "doc_id": doc_id,
            "summary": summary,
            "max_length": max_length
        }
        
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
        
        return {
            "message": "All documents cleared successfully"
        }
        
    except Exception as e:
        logger.error(f"Error clearing documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/evaluate")
async def evaluate_answer(
    question: str = Body(...),
    answer: str = Body(...),
    context: str = Body(...)
):
    """
    Evaluate the quality of an answer
    
    - **question**: Original question
    - **answer**: Generated answer
    - **context**: Context used for generation
    """
    try:
        evaluation = await generator.evaluate_answer_quality(
            question=question,
            answer=answer,
            context=context
        )
        
        return evaluation
        
    except Exception as e:
        logger.error(f"Error evaluating answer: {e}")
        raise HTTPException(status_code=500, detail=str(e))