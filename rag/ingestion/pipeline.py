"""Full document ingestion pipeline."""

from pathlib import Path
from dataclasses import dataclass

from rag.ingestion.loaders import DocumentLoader, Document
from rag.ingestion.chunker import TextChunker, TextChunk
from rag.store.chroma_store import ChromaStore


@dataclass
class IngestResult:
    """Result of ingestion operation."""
    total_documents: int
    total_chunks: int
    chunk_ids: list[str]


class IngestPipeline:
    """Orchestrates document ingestion into vector store."""
    
    def __init__(
        self,
        store: ChromaStore | None = None,
        chunker: TextChunker | None = None,
        chunk_size: int = 512,
        chunk_overlap: int = 50
    ):
        self.store = store or ChromaStore.instance()
        self.chunker = chunker or TextChunker(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )
    
    async def ingest_file(self, path: str | Path) -> IngestResult:
        """Ingest a single file."""
        from tracing.tracer import Tracer
        from tracing.models import SpanType, SpanStatus
        
        tracer = Tracer.instance()
        span = tracer.start_span(
            SpanType.RETRIEVAL,
            name="ingest_file",
            input_data={"path": str(path)}
        )
        
        try:
            # Load document
            document = DocumentLoader.load(path)
            
            # Chunk document
            chunks = self.chunker.chunk(document.content, document.metadata)
            
            # Store chunks
            chunk_ids = await self._store_chunks(chunks)
            
            result = IngestResult(
                total_documents=1,
                total_chunks=len(chunks),
                chunk_ids=chunk_ids
            )
            
            tracer.end_span(span, status=SpanStatus.SUCCESS, output_data={
                "chunks_created": len(chunks),
                "chunk_ids": chunk_ids[:5]  # First 5 IDs
            })
            return result
            
        except Exception as e:
            tracer.end_span(span, SpanStatus.ERROR, error=str(e))
            raise
    
    async def ingest_directory(
        self,
        directory: str | Path,
        recursive: bool = True
    ) -> IngestResult:
        """Ingest all documents from a directory."""
        from tracing.tracer import Tracer
        from tracing.models import SpanType, SpanStatus
        
        tracer = Tracer.instance()
        span = tracer.start_span(
            SpanType.RETRIEVAL,
            name="ingest_directory",
            input_data={"directory": str(directory), "recursive": recursive}
        )
        
        try:
            # Load all documents
            documents = DocumentLoader.load_directory(directory, recursive)
            
            if not documents:
                result = IngestResult(
                    total_documents=0,
                    total_chunks=0,
                    chunk_ids=[]
                )
                tracer.end_span(span, status=SpanStatus.SUCCESS, output_data={"message": "No documents found"})
                return result
            
            # Chunk all documents
            all_chunks: list[TextChunk] = []
            for doc in documents:
                chunks = self.chunker.chunk(doc.content, doc.metadata)
                all_chunks.extend(chunks)
            
            # Store all chunks
            chunk_ids = await self._store_chunks(all_chunks)
            
            result = IngestResult(
                total_documents=len(documents),
                total_chunks=len(all_chunks),
                chunk_ids=chunk_ids
            )
            
            tracer.end_span(span, status=SpanStatus.SUCCESS, output_data={
                "documents_processed": len(documents),
                "chunks_created": len(all_chunks)
            })
            return result
            
        except Exception as e:
            tracer.end_span(span, SpanStatus.ERROR, error=str(e))
            raise
    
    async def ingest_text(
        self,
        text: str,
        metadata: dict | None = None
    ) -> IngestResult:
        """Ingest raw text directly."""
        from tracing.tracer import Tracer
        from tracing.models import SpanType, SpanStatus
        
        tracer = Tracer.instance()
        span = tracer.start_span(
            SpanType.RETRIEVAL,
            name="ingest_text",
            input_data={"text_length": len(text)}
        )
        
        try:
            # Chunk text
            chunks = self.chunker.chunk(text, metadata or {})
            
            # Store chunks
            chunk_ids = await self._store_chunks(chunks)
            
            result = IngestResult(
                total_documents=1,
                total_chunks=len(chunks),
                chunk_ids=chunk_ids
            )
            
            tracer.end_span(span, status=SpanStatus.SUCCESS, output_data={
                "chunks_created": len(chunks)
            })
            return result
            
        except Exception as e:
            tracer.end_span(span, SpanStatus.ERROR, error=str(e))
            raise
    
    async def _store_chunks(self, chunks: list[TextChunk]) -> list[str]:
        """Store chunks in vector store."""
        if not chunks:
            return []
        
        documents = [chunk.content for chunk in chunks]
        metadatas = [chunk.metadata for chunk in chunks]
        
        return await self.store.add(documents=documents, metadatas=metadatas)
