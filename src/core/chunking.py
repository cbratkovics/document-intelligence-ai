from typing import List, Dict, Any
import re
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document
import logging

from .config import settings

logger = logging.getLogger(__name__)


class DocumentChunker:
    """Handles document chunking with various strategies"""
    
    def __init__(
        self,
        chunk_size: int = None,
        chunk_overlap: int = None,
        length_function: callable = len
    ):
        self.chunk_size = chunk_size or settings.chunk_size
        self.chunk_overlap = chunk_overlap or settings.chunk_overlap
        self.length_function = length_function
        
        # Initialize the text splitter
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            length_function=self.length_function,
            separators=["\n\n", "\n", ". ", " ", ""],
            keep_separator=True
        )
    
    def chunk_document(self, document: Document) -> List[Document]:
        """
        Split a document into chunks
        
        Args:
            document: Document to chunk
            
        Returns:
            List of chunked documents with metadata
        """
        try:
            # Split the document
            chunks = self.text_splitter.split_documents([document])
            
            # Enhance chunk metadata
            for i, chunk in enumerate(chunks):
                chunk.metadata.update({
                    'chunk_index': i,
                    'total_chunks': len(chunks),
                    'chunk_size': len(chunk.page_content),
                    'original_doc_id': document.metadata.get('doc_id', ''),
                    'source': document.metadata.get('source', '')
                })
            
            logger.info(
                f"Split document '{document.metadata.get('filename', 'Unknown')}' "
                f"into {len(chunks)} chunks"
            )
            
            return chunks
            
        except Exception as e:
            logger.error(f"Error chunking document: {e}")
            raise
    
    def chunk_text(self, text: str, metadata: Dict[str, Any] = None) -> List[Document]:
        """
        Split raw text into chunks
        
        Args:
            text: Text to chunk
            metadata: Optional metadata to attach to chunks
            
        Returns:
            List of Document objects
        """
        if metadata is None:
            metadata = {}
        
        # Create a temporary document
        temp_doc = Document(page_content=text, metadata=metadata)
        
        return self.chunk_document(temp_doc)
    
    def smart_chunk_document(self, document: Document) -> List[Document]:
        """
        Smart chunking that tries to preserve semantic boundaries
        
        Args:
            document: Document to chunk
            
        Returns:
            List of chunked documents
        """
        text = document.page_content
        metadata = document.metadata
        
        # Check if it's a structured document (markdown, rst)
        if metadata.get('extension') in ['.md', '.rst']:
            return self._chunk_structured_document(document)
        
        # For PDFs, try to preserve page boundaries when possible
        if metadata.get('extension') == '.pdf' and '[Page' in text:
            return self._chunk_pdf_document(document)
        
        # Default to standard chunking
        return self.chunk_document(document)
    
    def _chunk_structured_document(self, document: Document) -> List[Document]:
        """Chunk structured documents (markdown, rst) by sections"""
        text = document.page_content
        chunks = []
        
        # Split by headers (markdown style)
        sections = re.split(r'\n(?=#+ )', text)
        
        current_chunk = ""
        for section in sections:
            if len(current_chunk) + len(section) > self.chunk_size:
                if current_chunk:
                    chunks.append(Document(
                        page_content=current_chunk.strip(),
                        metadata=document.metadata.copy()
                    ))
                current_chunk = section
            else:
                current_chunk += "\n" + section if current_chunk else section
        
        if current_chunk:
            chunks.append(Document(
                page_content=current_chunk.strip(),
                metadata=document.metadata.copy()
            ))
        
        # If no sections found or too few chunks, fall back to standard chunking
        if len(chunks) <= 1:
            return self.chunk_document(document)
        
        # Update metadata
        for i, chunk in enumerate(chunks):
            chunk.metadata.update({
                'chunk_index': i,
                'total_chunks': len(chunks),
                'chunk_type': 'section'
            })
        
        return chunks
    
    def _chunk_pdf_document(self, document: Document) -> List[Document]:
        """Chunk PDF documents trying to preserve page boundaries"""
        text = document.page_content
        chunks = []
        
        # Split by page markers
        pages = re.split(r'\[Page \d+\]\n', text)
        page_numbers = re.findall(r'\[Page (\d+)\]', text)
        
        for i, (page_text, page_num) in enumerate(zip(pages[1:], page_numbers)):
            if not page_text.strip():
                continue
            
            # If page is too long, chunk it further
            if len(page_text) > self.chunk_size:
                page_doc = Document(
                    page_content=page_text,
                    metadata={**document.metadata, 'page_number': int(page_num)}
                )
                page_chunks = self.chunk_document(page_doc)
                chunks.extend(page_chunks)
            else:
                chunks.append(Document(
                    page_content=page_text.strip(),
                    metadata={
                        **document.metadata,
                        'page_number': int(page_num),
                        'chunk_type': 'page'
                    }
                ))
        
        # Update metadata
        for i, chunk in enumerate(chunks):
            chunk.metadata.update({
                'chunk_index': i,
                'total_chunks': len(chunks)
            })
        
        return chunks if chunks else self.chunk_document(document)
    
    def get_chunk_statistics(self, chunks: List[Document]) -> Dict[str, Any]:
        """Get statistics about chunks"""
        if not chunks:
            return {
                'total_chunks': 0,
                'avg_chunk_size': 0,
                'min_chunk_size': 0,
                'max_chunk_size': 0,
                'total_size': 0
            }
        
        chunk_sizes = [len(chunk.page_content) for chunk in chunks]
        
        return {
            'total_chunks': len(chunks),
            'avg_chunk_size': sum(chunk_sizes) / len(chunk_sizes),
            'min_chunk_size': min(chunk_sizes),
            'max_chunk_size': max(chunk_sizes),
            'total_size': sum(chunk_sizes)
        }