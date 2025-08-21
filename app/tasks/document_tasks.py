from celery import Task, current_task, group, chain
from celery.result import AsyncResult
from typing import List, Dict, Any, Optional
import logging
import time
from pathlib import Path
import hashlib
import json
from datetime import datetime

from app.tasks.celery_app import app
from app.chunking.strategies import ChunkingFactory, ChunkingStrategy, ChunkingConfig
from app.embeddings.factory import EmbeddingFactory

logger = logging.getLogger(__name__)


class CallbackTask(Task):
    def on_success(self, retval, task_id, args, kwargs):
        logger.info(f"Task {task_id} succeeded with result: {retval}")
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error(f"Task {task_id} failed with exception: {exc}")


@app.task(bind=True, base=CallbackTask, name="process_document")
def process_document(
    self,
    file_path: str,
    document_id: str,
    metadata: Dict[str, Any] = None,
    chunking_strategy: str = "semantic",
    embedding_model: str = "text-embedding-ada-002"
) -> Dict[str, Any]:
    try:
        self.update_state(state="PROCESSING", meta={"stage": "reading_file"})
        
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Document not found: {file_path}")
        
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        file_hash = hashlib.md5(content.encode()).hexdigest()
        
        self.update_state(state="PROCESSING", meta={"stage": "chunking", "progress": 25})
        
        config = ChunkingConfig(
            chunk_size=512,
            chunk_overlap=128,
            preserve_sentences=True
        )
        
        chunker = ChunkingFactory.create_chunker(
            ChunkingStrategy(chunking_strategy),
            config
        )
        
        chunks = chunker.chunk(content, metadata)
        
        self.update_state(state="PROCESSING", meta={"stage": "embedding", "progress": 50})
        
        embedding_tasks = []
        for i, chunk in enumerate(chunks):
            task = generate_embeddings.s(
                chunk.content,
                f"{document_id}_chunk_{i}",
                embedding_model
            )
            embedding_tasks.append(task)
        
        job = group(embedding_tasks).apply_async()
        embeddings_results = job.get(timeout=300)
        
        self.update_state(state="PROCESSING", meta={"stage": "indexing", "progress": 75})
        
        index_task = index_document.delay(
            document_id=document_id,
            chunks=[c.content for c in chunks],
            embeddings=[r["embedding"] for r in embeddings_results],
            metadata={
                **(metadata or {}),
                "file_path": file_path,
                "file_hash": file_hash,
                "num_chunks": len(chunks),
                "processed_at": datetime.utcnow().isoformat()
            }
        )
        
        index_result = index_task.get(timeout=60)
        
        return {
            "document_id": document_id,
            "file_path": file_path,
            "file_hash": file_hash,
            "num_chunks": len(chunks),
            "total_tokens": sum(len(c.content.split()) for c in chunks),
            "metadata": metadata,
            "indexed": index_result.get("success", False),
            "processing_time": time.time()
        }
    
    except Exception as e:
        logger.error(f"Error processing document {document_id}: {e}")
        self.update_state(
            state="FAILURE",
            meta={"error": str(e), "document_id": document_id}
        )
        raise


@app.task(bind=True, name="batch_process_documents")
def batch_process_documents(
    self,
    file_paths: List[str],
    batch_id: str,
    metadata: Dict[str, Any] = None,
    chunking_strategy: str = "semantic",
    embedding_model: str = "text-embedding-ada-002"
) -> Dict[str, Any]:
    try:
        total_documents = len(file_paths)
        processed = 0
        failed = 0
        results = []
        
        self.update_state(
            state="PROCESSING",
            meta={
                "batch_id": batch_id,
                "total": total_documents,
                "processed": processed,
                "failed": failed
            }
        )
        
        for i, file_path in enumerate(file_paths):
            try:
                doc_id = f"{batch_id}_doc_{i}"
                
                result = process_document.apply_async(
                    args=[file_path, doc_id],
                    kwargs={
                        "metadata": metadata,
                        "chunking_strategy": chunking_strategy,
                        "embedding_model": embedding_model
                    }
                )
                
                doc_result = result.get(timeout=300)
                results.append(doc_result)
                processed += 1
                
            except Exception as e:
                logger.error(f"Failed to process document {file_path}: {e}")
                failed += 1
                results.append({
                    "file_path": file_path,
                    "error": str(e),
                    "status": "failed"
                })
            
            self.update_state(
                state="PROCESSING",
                meta={
                    "batch_id": batch_id,
                    "total": total_documents,
                    "processed": processed,
                    "failed": failed,
                    "progress": int((i + 1) / total_documents * 100)
                }
            )
        
        return {
            "batch_id": batch_id,
            "total_documents": total_documents,
            "processed": processed,
            "failed": failed,
            "results": results,
            "completion_time": datetime.utcnow().isoformat()
        }
    
    except Exception as e:
        logger.error(f"Batch processing failed for {batch_id}: {e}")
        raise


@app.task(name="generate_embeddings")
def generate_embeddings(
    text: str,
    chunk_id: str,
    model: str = "text-embedding-ada-002"
) -> Dict[str, Any]:
    try:
        embedder = EmbeddingFactory.create_embeddings(model)
        embedding = embedder.embed_query(text)
        
        return {
            "chunk_id": chunk_id,
            "embedding": embedding,
            "model": model,
            "dimension": len(embedding)
        }
    
    except Exception as e:
        logger.error(f"Failed to generate embeddings for {chunk_id}: {e}")
        raise


@app.task(name="index_document")
def index_document(
    document_id: str,
    chunks: List[str],
    embeddings: List[List[float]],
    metadata: Dict[str, Any] = None
) -> Dict[str, Any]:
    try:
        from app.retrieval.hybrid_search import HybridSearchEngine
        
        search_engine = HybridSearchEngine()
        
        doc_ids = [f"{document_id}_chunk_{i}" for i in range(len(chunks))]
        
        chunk_metadata = []
        for i, chunk in enumerate(chunks):
            chunk_meta = {
                **(metadata or {}),
                "chunk_index": i,
                "chunk_text": chunk[:200],
                "document_id": document_id
            }
            chunk_metadata.append(chunk_meta)
        
        search_engine.add_documents(
            documents=chunks,
            embeddings=embeddings,
            doc_ids=doc_ids,
            metadata=chunk_metadata
        )
        
        return {
            "success": True,
            "document_id": document_id,
            "chunks_indexed": len(chunks),
            "index_time": datetime.utcnow().isoformat()
        }
    
    except Exception as e:
        logger.error(f"Failed to index document {document_id}: {e}")
        raise


@app.task(name="get_task_status")
def get_task_status(task_id: str) -> Dict[str, Any]:
    try:
        result = AsyncResult(task_id, app=app)
        
        return {
            "task_id": task_id,
            "state": result.state,
            "info": result.info,
            "result": result.result if result.ready() else None,
            "ready": result.ready(),
            "successful": result.successful() if result.ready() else None,
            "failed": result.failed() if result.ready() else None
        }
    
    except Exception as e:
        logger.error(f"Failed to get task status for {task_id}: {e}")
        return {
            "task_id": task_id,
            "error": str(e),
            "state": "ERROR"
        }


@app.task(name="cleanup_old_documents")
def cleanup_old_documents(days_old: int = 30) -> Dict[str, Any]:
    try:
        from datetime import datetime, timedelta
        
        cutoff_date = datetime.utcnow() - timedelta(days=days_old)
        
        logger.info(f"Cleaning up documents older than {cutoff_date}")
        
        return {
            "success": True,
            "cutoff_date": cutoff_date.isoformat(),
            "documents_removed": 0
        }
    
    except Exception as e:
        logger.error(f"Cleanup failed: {e}")
        raise