"""ChromaDB vector store wrapper."""

import os
from pathlib import Path
from dataclasses import dataclass
from typing import Any

import chromadb
from chromadb.config import Settings

from rag.embeddings.embedding_router import EmbeddingRouter


@dataclass
class SearchResult:
    """Single search result."""
    id: str
    content: str
    metadata: dict[str, Any]
    score: float


class ChromaStore:
    """ChromaDB wrapper for vector storage."""
    
    _instance: "ChromaStore | None" = None
    
    def __init__(
        self,
        persist_dir: str | None = None,
        collection_name: str = "documents"
    ):
        persist_path = persist_dir or os.getenv(
            "CHROMA_PERSIST_DIR",
            str(Path.home() / ".agent-platform" / "chroma")
        )
        Path(persist_path).mkdir(parents=True, exist_ok=True)
        
        self.client = chromadb.Client(Settings(
            chroma_db_impl="duckdb+parquet",
            persist_directory=persist_path,
            anonymized_telemetry=False
        ))
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"}
        )
        self.embedder = EmbeddingRouter.instance()
    
    @classmethod
    def instance(cls) -> "ChromaStore":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def reset(cls) -> None:
        """Reset singleton for testing."""
        cls._instance = None
    
    async def add(
        self,
        documents: list[str],
        metadatas: list[dict[str, Any]] | None = None,
        ids: list[str] | None = None
    ) -> list[str]:
        """Add documents to the store."""
        from tracing.tracer import Tracer
        from tracing.models import SpanType, SpanStatus
        
        tracer = Tracer.instance()
        span = tracer.start_span(
            SpanType.RETRIEVAL,
            name="chroma_add",
            input_data={"document_count": len(documents)}
        )
        
        try:
            # Generate IDs if not provided
            if ids is None:
                import hashlib
                ids = [
                    hashlib.sha256(doc.encode()).hexdigest()[:16]
                    for doc in documents
                ]
            
            # Generate embeddings
            embeddings = await self.embedder.embed(documents)
            
            # Add to collection
            self.collection.add(
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas or [{}] * len(documents),
                ids=ids
            )
            
            tracer.end_span(span, status=SpanStatus.SUCCESS, output_data={
                "added_count": len(documents),
                "ids": ids
            })
            return ids
            
        except Exception as e:
            tracer.end_span(span, SpanStatus.ERROR, error=str(e))
            raise
    
    async def search(
        self,
        query: str,
        top_k: int = 5,
        filter_metadata: dict[str, Any] | None = None
    ) -> list[SearchResult]:
        """Search for similar documents."""
        from tracing.tracer import Tracer
        from tracing.models import SpanType, SpanStatus
        
        tracer = Tracer.instance()
        span = tracer.start_span(
            SpanType.RETRIEVAL,
            name="chroma_search",
            input_data={"query": query[:200], "top_k": top_k}
        )
        
        try:
            # Generate query embedding
            query_embedding = await self.embedder.embed([query])
            
            # Search
            results = self.collection.query(
                query_embeddings=query_embedding,
                n_results=top_k,
                where=filter_metadata
            )
            
            # Convert to SearchResult objects
            search_results = []
            if results["ids"] and results["ids"][0]:
                for i, doc_id in enumerate(results["ids"][0]):
                    search_results.append(SearchResult(
                        id=doc_id,
                        content=results["documents"][0][i] if results["documents"] else "",
                        metadata=results["metadatas"][0][i] if results["metadatas"] else {},
                        score=1.0 - (results["distances"][0][i] if results["distances"] else 0)
                    ))
            
            tracer.end_span(span, status=SpanStatus.SUCCESS, output_data={
                "result_count": len(search_results),
                "top_score": search_results[0].score if search_results else 0
            })
            return search_results
            
        except Exception as e:
            tracer.end_span(span, SpanStatus.ERROR, error=str(e))
            raise
    
    async def delete(self, ids: list[str]) -> None:
        """Delete documents by ID."""
        self.collection.delete(ids=ids)
    
    def count(self) -> int:
        """Get total document count."""
        return self.collection.count()
