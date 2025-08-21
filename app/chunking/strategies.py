from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from abc import ABC, abstractmethod
import re
import nltk
from nltk.tokenize import sent_tokenize, word_tokenize
import logging
from enum import Enum

try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt', quiet=True)

logger = logging.getLogger(__name__)


class ChunkingStrategy(str, Enum):
    FIXED_SIZE = "fixed_size"
    SLIDING_WINDOW = "sliding_window"
    SENTENCE_BASED = "sentence_based"
    PARAGRAPH_BASED = "paragraph_based"
    SEMANTIC = "semantic"
    RECURSIVE = "recursive"
    MARKDOWN_AWARE = "markdown_aware"


@dataclass
class Chunk:
    content: str
    metadata: Dict[str, Any]
    start_index: int
    end_index: int
    chunk_id: str
    overlap_with_previous: int = 0
    overlap_with_next: int = 0


@dataclass
class ChunkingConfig:
    chunk_size: int = 512
    chunk_overlap: int = 128
    min_chunk_size: int = 100
    max_chunk_size: int = 2000
    separator: str = "\n"
    preserve_sentences: bool = True
    preserve_paragraphs: bool = False
    use_token_count: bool = True


class BaseChunkingStrategy(ABC):
    def __init__(self, config: ChunkingConfig = None):
        self.config = config or ChunkingConfig()
    
    @abstractmethod
    def chunk(self, text: str, metadata: Dict[str, Any] = None) -> List[Chunk]:
        pass
    
    def _estimate_tokens(self, text: str) -> int:
        return len(text.split()) * 1.3
    
    def _create_chunk(
        self,
        content: str,
        start_index: int,
        end_index: int,
        chunk_number: int,
        metadata: Dict[str, Any] = None
    ) -> Chunk:
        return Chunk(
            content=content,
            metadata=metadata or {},
            start_index=start_index,
            end_index=end_index,
            chunk_id=f"chunk_{chunk_number}"
        )


class FixedSizeChunking(BaseChunkingStrategy):
    def chunk(self, text: str, metadata: Dict[str, Any] = None) -> List[Chunk]:
        chunks = []
        chunk_size = self.config.chunk_size
        
        if self.config.use_token_count:
            words = text.split()
            tokens_per_chunk = int(chunk_size / 1.3)
            
            for i in range(0, len(words), tokens_per_chunk):
                chunk_words = words[i:i + tokens_per_chunk]
                chunk_text = " ".join(chunk_words)
                
                start_index = text.find(chunk_words[0]) if chunk_words else 0
                end_index = start_index + len(chunk_text)
                
                chunks.append(self._create_chunk(
                    chunk_text, start_index, end_index, len(chunks), metadata
                ))
        else:
            for i in range(0, len(text), chunk_size):
                chunk_text = text[i:i + chunk_size]
                chunks.append(self._create_chunk(
                    chunk_text, i, i + len(chunk_text), len(chunks), metadata
                ))
        
        return chunks


class SlidingWindowChunking(BaseChunkingStrategy):
    def chunk(self, text: str, metadata: Dict[str, Any] = None) -> List[Chunk]:
        chunks = []
        chunk_size = self.config.chunk_size
        overlap = self.config.chunk_overlap
        stride = chunk_size - overlap
        
        if stride <= 0:
            stride = chunk_size // 2
        
        if self.config.use_token_count:
            words = text.split()
            tokens_per_chunk = int(chunk_size / 1.3)
            tokens_overlap = int(overlap / 1.3)
            stride_tokens = tokens_per_chunk - tokens_overlap
            
            for i in range(0, len(words), stride_tokens):
                chunk_words = words[i:i + tokens_per_chunk]
                if not chunk_words:
                    break
                
                chunk_text = " ".join(chunk_words)
                start_index = text.find(chunk_words[0])
                end_index = start_index + len(chunk_text)
                
                chunk = self._create_chunk(
                    chunk_text, start_index, end_index, len(chunks), metadata
                )
                
                if i > 0:
                    chunk.overlap_with_previous = tokens_overlap
                if i + tokens_per_chunk < len(words):
                    chunk.overlap_with_next = tokens_overlap
                
                chunks.append(chunk)
        else:
            for i in range(0, len(text), stride):
                chunk_text = text[i:i + chunk_size]
                if not chunk_text:
                    break
                
                chunk = self._create_chunk(
                    chunk_text, i, i + len(chunk_text), len(chunks), metadata
                )
                
                if i > 0:
                    chunk.overlap_with_previous = overlap
                if i + chunk_size < len(text):
                    chunk.overlap_with_next = overlap
                
                chunks.append(chunk)
        
        return chunks


class SentenceBasedChunking(BaseChunkingStrategy):
    def chunk(self, text: str, metadata: Dict[str, Any] = None) -> List[Chunk]:
        sentences = sent_tokenize(text)
        chunks = []
        current_chunk = []
        current_size = 0
        start_index = 0
        
        for sentence in sentences:
            sentence_size = self._estimate_tokens(sentence) if self.config.use_token_count else len(sentence)
            
            if current_size + sentence_size > self.config.chunk_size and current_chunk:
                chunk_text = " ".join(current_chunk)
                end_index = start_index + len(chunk_text)
                
                chunks.append(self._create_chunk(
                    chunk_text, start_index, end_index, len(chunks), metadata
                ))
                
                if self.config.chunk_overlap > 0:
                    overlap_sentences = int(len(current_chunk) * 0.2)
                    current_chunk = current_chunk[-overlap_sentences:] if overlap_sentences > 0 else []
                    current_size = sum(
                        self._estimate_tokens(s) if self.config.use_token_count else len(s)
                        for s in current_chunk
                    )
                else:
                    current_chunk = []
                    current_size = 0
                
                start_index = end_index + 1
            
            current_chunk.append(sentence)
            current_size += sentence_size
        
        if current_chunk:
            chunk_text = " ".join(current_chunk)
            chunks.append(self._create_chunk(
                chunk_text, start_index, start_index + len(chunk_text), len(chunks), metadata
            ))
        
        return chunks


class SemanticChunking(BaseChunkingStrategy):
    def __init__(self, config: ChunkingConfig = None, similarity_threshold: float = 0.7):
        super().__init__(config)
        self.similarity_threshold = similarity_threshold
    
    def _calculate_sentence_similarity(self, sent1: str, sent2: str) -> float:
        words1 = set(word_tokenize(sent1.lower()))
        words2 = set(word_tokenize(sent2.lower()))
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union) if union else 0.0
    
    def chunk(self, text: str, metadata: Dict[str, Any] = None) -> List[Chunk]:
        sentences = sent_tokenize(text)
        chunks = []
        current_chunk = []
        start_index = 0
        
        for i, sentence in enumerate(sentences):
            if not current_chunk:
                current_chunk.append(sentence)
                continue
            
            similarity = self._calculate_sentence_similarity(
                current_chunk[-1], sentence
            )
            
            current_size = sum(
                self._estimate_tokens(s) if self.config.use_token_count else len(s)
                for s in current_chunk
            )
            
            if (similarity < self.similarity_threshold or 
                current_size > self.config.chunk_size) and current_chunk:
                
                chunk_text = " ".join(current_chunk)
                end_index = start_index + len(chunk_text)
                
                chunks.append(self._create_chunk(
                    chunk_text, start_index, end_index, len(chunks), metadata
                ))
                
                current_chunk = [sentence]
                start_index = end_index + 1
            else:
                current_chunk.append(sentence)
        
        if current_chunk:
            chunk_text = " ".join(current_chunk)
            chunks.append(self._create_chunk(
                chunk_text, start_index, start_index + len(chunk_text), len(chunks), metadata
            ))
        
        return chunks


class RecursiveChunking(BaseChunkingStrategy):
    def __init__(self, config: ChunkingConfig = None):
        super().__init__(config)
        self.separators = ["\n\n", "\n", ". ", ", ", " "]
    
    def _split_text(self, text: str, separators: List[str]) -> List[str]:
        if not separators:
            return [text]
        
        separator = separators[0]
        splits = text.split(separator)
        
        final_chunks = []
        for split in splits:
            size = self._estimate_tokens(split) if self.config.use_token_count else len(split)
            
            if size <= self.config.chunk_size:
                final_chunks.append(split)
            elif len(separators) > 1:
                final_chunks.extend(self._split_text(split, separators[1:]))
            else:
                final_chunks.append(split)
        
        return final_chunks
    
    def chunk(self, text: str, metadata: Dict[str, Any] = None) -> List[Chunk]:
        splits = self._split_text(text, self.separators)
        chunks = []
        current_chunk = []
        current_size = 0
        start_index = 0
        
        for split in splits:
            split_size = self._estimate_tokens(split) if self.config.use_token_count else len(split)
            
            if current_size + split_size > self.config.chunk_size and current_chunk:
                chunk_text = " ".join(current_chunk)
                end_index = start_index + len(chunk_text)
                
                chunks.append(self._create_chunk(
                    chunk_text, start_index, end_index, len(chunks), metadata
                ))
                
                current_chunk = []
                current_size = 0
                start_index = end_index + 1
            
            current_chunk.append(split)
            current_size += split_size
        
        if current_chunk:
            chunk_text = " ".join(current_chunk)
            chunks.append(self._create_chunk(
                chunk_text, start_index, start_index + len(chunk_text), len(chunks), metadata
            ))
        
        return chunks


class MarkdownAwareChunking(BaseChunkingStrategy):
    def _identify_sections(self, text: str) -> List[Tuple[str, str, int, int]]:
        sections = []
        lines = text.split('\n')
        current_section = []
        current_header = ""
        start_index = 0
        char_index = 0
        
        for line in lines:
            if re.match(r'^#{1,6}\s+', line):
                if current_section:
                    section_text = '\n'.join(current_section)
                    sections.append((
                        current_header,
                        section_text,
                        start_index,
                        char_index
                    ))
                    start_index = char_index + len(line) + 1
                
                current_header = line
                current_section = []
            else:
                current_section.append(line)
            
            char_index += len(line) + 1
        
        if current_section:
            section_text = '\n'.join(current_section)
            sections.append((
                current_header,
                section_text,
                start_index,
                char_index
            ))
        
        return sections
    
    def chunk(self, text: str, metadata: Dict[str, Any] = None) -> List[Chunk]:
        sections = self._identify_sections(text)
        chunks = []
        
        for header, content, start, end in sections:
            full_section = f"{header}\n{content}" if header else content
            section_size = self._estimate_tokens(full_section) if self.config.use_token_count else len(full_section)
            
            if section_size <= self.config.chunk_size:
                chunk_metadata = {**(metadata or {}), "header": header}
                chunks.append(self._create_chunk(
                    full_section, start, end, len(chunks), chunk_metadata
                ))
            else:
                sub_chunker = RecursiveChunking(self.config)
                sub_chunks = sub_chunker.chunk(full_section, metadata)
                
                for sub_chunk in sub_chunks:
                    sub_chunk.metadata["header"] = header
                    sub_chunk.start_index += start
                    sub_chunk.end_index += start
                    sub_chunk.chunk_id = f"chunk_{len(chunks)}"
                    chunks.append(sub_chunk)
        
        return chunks


class ChunkingFactory:
    _strategies = {
        ChunkingStrategy.FIXED_SIZE: FixedSizeChunking,
        ChunkingStrategy.SLIDING_WINDOW: SlidingWindowChunking,
        ChunkingStrategy.SENTENCE_BASED: SentenceBasedChunking,
        ChunkingStrategy.SEMANTIC: SemanticChunking,
        ChunkingStrategy.RECURSIVE: RecursiveChunking,
        ChunkingStrategy.MARKDOWN_AWARE: MarkdownAwareChunking
    }
    
    @classmethod
    def create_chunker(
        cls,
        strategy: ChunkingStrategy,
        config: ChunkingConfig = None
    ) -> BaseChunkingStrategy:
        if strategy not in cls._strategies:
            raise ValueError(f"Unknown chunking strategy: {strategy}")
        
        return cls._strategies[strategy](config)
    
    @classmethod
    def auto_select_strategy(cls, text: str, config: ChunkingConfig = None) -> BaseChunkingStrategy:
        if re.search(r'^#{1,6}\s+', text, re.MULTILINE):
            return cls.create_chunker(ChunkingStrategy.MARKDOWN_AWARE, config)
        
        elif len(sent_tokenize(text)) > 10:
            return cls.create_chunker(ChunkingStrategy.SEMANTIC, config)
        
        elif len(text) < 1000:
            return cls.create_chunker(ChunkingStrategy.SENTENCE_BASED, config)
        
        else:
            return cls.create_chunker(ChunkingStrategy.RECURSIVE, config)