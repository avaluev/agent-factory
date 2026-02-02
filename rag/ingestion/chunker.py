"""Text chunking for document processing."""

from dataclasses import dataclass
from typing import Any


@dataclass
class TextChunk:
    """A chunk of text with metadata."""
    content: str
    metadata: dict[str, Any]
    chunk_index: int


class TextChunker:
    """Recursive text chunker with overlap support."""
    
    DEFAULT_SEPARATORS = ["\n\n", "\n", ". ", " ", ""]
    
    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 50,
        separators: list[str] | None = None
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators or self.DEFAULT_SEPARATORS
    
    def chunk(
        self,
        text: str,
        metadata: dict[str, Any] | None = None
    ) -> list[TextChunk]:
        """Split text into chunks with overlap."""
        metadata = metadata or {}
        chunks = self._recursive_split(text, self.separators)
        
        # Merge small chunks and handle overlap
        merged_chunks = self._merge_chunks(chunks)
        
        return [
            TextChunk(
                content=chunk,
                metadata={**metadata, "chunk_index": i},
                chunk_index=i
            )
            for i, chunk in enumerate(merged_chunks)
        ]
    
    def _recursive_split(
        self,
        text: str,
        separators: list[str]
    ) -> list[str]:
        """Recursively split text using separators."""
        if not text:
            return []
        
        if len(text) <= self.chunk_size:
            return [text]
        
        # Try each separator
        for sep in separators:
            if sep == "":
                # Last resort: character-level split
                return self._character_split(text)
            
            if sep in text:
                splits = text.split(sep)
                results = []
                current = ""
                
                for split in splits:
                    # Check if adding this split would exceed chunk size
                    test_chunk = current + sep + split if current else split
                    
                    if len(test_chunk) <= self.chunk_size:
                        current = test_chunk
                    else:
                        if current:
                            results.append(current)
                        
                        # If single split is too large, recurse with next separator
                        if len(split) > self.chunk_size:
                            next_seps = separators[separators.index(sep) + 1:]
                            results.extend(self._recursive_split(split, next_seps))
                            current = ""
                        else:
                            current = split
                
                if current:
                    results.append(current)
                
                return results
        
        return [text]
    
    def _character_split(self, text: str) -> list[str]:
        """Split text at character level."""
        chunks = []
        for i in range(0, len(text), self.chunk_size):
            chunks.append(text[i:i + self.chunk_size])
        return chunks
    
    def _merge_chunks(self, chunks: list[str]) -> list[str]:
        """Merge small chunks and add overlap."""
        if not chunks:
            return []
        
        result = []
        i = 0
        
        while i < len(chunks):
            current = chunks[i]
            
            # Try to merge with next chunks if current is small
            while (
                i + 1 < len(chunks) and 
                len(current) + len(chunks[i + 1]) + 1 <= self.chunk_size
            ):
                i += 1
                current = current + " " + chunks[i]
            
            # Add overlap from previous chunk
            if result and self.chunk_overlap > 0:
                prev = result[-1]
                overlap_text = prev[-self.chunk_overlap:] if len(prev) > self.chunk_overlap else prev
                # Only add overlap if it makes sense (ends with space or punctuation)
                if overlap_text and not current.startswith(overlap_text):
                    # Find a good break point for overlap
                    break_idx = overlap_text.rfind(" ")
                    if break_idx > 0:
                        overlap_text = overlap_text[break_idx + 1:]
                    current = overlap_text + " " + current
            
            result.append(current.strip())
            i += 1
        
        return result
