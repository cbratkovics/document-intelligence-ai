import os
import hashlib
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import mimetypes
from pathlib import Path
import logging

from pypdf import PdfReader
from langchain.schema import Document

from ..core.config import settings

logger = logging.getLogger(__name__)


class DocumentLoader:
    """Handles loading and processing of various document types"""

    SUPPORTED_EXTENSIONS = {".txt", ".pdf", ".md", ".rst"}

    def __init__(self):
        self.data_dir = Path(settings.data_dir)
        self.data_dir.mkdir(exist_ok=True)

    def load_document(
        self, file_path: str, content: Optional[bytes] = None
    ) -> Document:
        """
        Load a document from file path or content

        Args:
            file_path: Path to the document
            content: Optional file content (for uploaded files)

        Returns:
            Document object with content and metadata
        """
        file_path = Path(file_path)

        # Get file extension
        extension = file_path.suffix.lower()

        if extension not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(f"Unsupported file type: {extension}")

        # Load content if not provided
        if content is None:
            with open(file_path, "rb") as f:
                content = f.read()

        # Generate document ID
        doc_id = self._generate_document_id(content)

        # Extract text based on file type
        if extension == ".pdf":
            text = self._extract_pdf_text(content)
        else:
            # For text files (.txt, .md, .rst)
            text = content.decode("utf-8", errors="ignore")

        # Create metadata
        metadata = {
            "source": str(file_path),
            "filename": file_path.name,
            "extension": extension,
            "doc_id": doc_id,
            "size": len(content),
            "created_at": datetime.utcnow().isoformat(),
            "mime_type": mimetypes.guess_type(str(file_path))[0],
        }

        return Document(page_content=text, metadata=metadata)

    def save_uploaded_file(self, filename: str, content: bytes) -> str:
        """
        Save an uploaded file to the data directory

        Args:
            filename: Original filename
            content: File content

        Returns:
            Path to saved file
        """
        # Generate safe filename
        safe_filename = self._sanitize_filename(filename)
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        final_filename = f"{timestamp}_{safe_filename}"

        # Save file
        file_path = self.data_dir / final_filename
        with open(file_path, "wb") as f:
            f.write(content)

        logger.info(f"Saved uploaded file: {file_path}")
        return str(file_path)

    def _extract_pdf_text(self, content: bytes) -> str:
        """Extract text from PDF content"""
        try:
            # Create a file-like object from bytes
            import io

            pdf_file = io.BytesIO(content)

            # Read PDF
            reader = PdfReader(pdf_file)
            text_parts = []

            for page_num, page in enumerate(reader.pages):
                try:
                    text = page.extract_text()
                    if text.strip():
                        text_parts.append(f"[Page {page_num + 1}]\n{text}")
                except Exception as e:
                    logger.warning(
                        f"Failed to extract text from page {page_num + 1}: {e}"
                    )

            return "\n\n".join(text_parts)
        except Exception as e:
            logger.error(f"Failed to extract PDF text: {e}")
            raise ValueError(f"Failed to process PDF: {str(e)}")

    def _generate_document_id(self, content: bytes) -> str:
        """Generate unique document ID based on content"""
        return hashlib.sha256(content).hexdigest()

    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for safe storage"""
        # Remove path components
        filename = os.path.basename(filename)

        # Replace problematic characters
        safe_chars = set(
            "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-_"
        )
        sanitized = "".join(c if c in safe_chars else "_" for c in filename)

        # Ensure it has an extension
        if "." not in sanitized:
            sanitized = sanitized + ".txt"

        return sanitized

    def list_documents(self) -> List[Dict[str, any]]:
        """List all documents in the data directory"""
        documents = []

        for file_path in self.data_dir.iterdir():
            if (
                file_path.is_file()
                and file_path.suffix.lower() in self.SUPPORTED_EXTENSIONS
            ):
                stat = file_path.stat()
                documents.append(
                    {
                        "filename": file_path.name,
                        "path": str(file_path),
                        "size": stat.st_size,
                        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        "extension": file_path.suffix.lower(),
                    }
                )

        return sorted(documents, key=lambda x: x["modified"], reverse=True)

    def delete_document(self, filename: str) -> bool:
        """Delete a document from the data directory"""
        file_path = self.data_dir / filename

        if file_path.exists() and file_path.is_file():
            file_path.unlink()
            logger.info(f"Deleted document: {filename}")
            return True

        return False
