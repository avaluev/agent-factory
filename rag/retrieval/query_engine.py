"""Query engine for semantic search."""

from dataclasses import dataclass
from typing import Any

from rag.store.chroma_store import ChromaStore, SearchResult


@dataclass
class QueryResult:
    """Result of a RAG query."""
    query: str
    results: list[SearchResult]
    context: str


class QueryEngine:
    """Semantic search query engine with tracing."""
    
    def __init__(
        self,
        store: ChromaStore | None = None,
        default_top_k: int = 5,
        score_threshold: float = 0.0
    ):
        self.store = store or ChromaStore.instance()
        self.default_top_k = default_top_k
        self.score_threshold = score_threshold
    
    async def query(
        self,
        query: str,
        top_k: int | None = None,
        filter_metadata: dict[str, Any] | None = None
    ) -> QueryResult:
        """Execute a semantic search query."""
        from tracing.tracer import Tracer
        from tracing.models import SpanType, SpanStatus
        
        tracer = Tracer.instance()
        span = tracer.start_span(
            SpanType.RETRIEVAL,
            name="rag_query",
            input_data={
                "query": query[:200],
                "top_k": top_k or self.default_top_k
            }
        )
        
        try:
            # Execute search
            results = await self.store.search(
                query=query,
                top_k=top_k or self.default_top_k,
                filter_metadata=filter_metadata
            )
            
            # Filter by score threshold
            filtered_results = [
                r for r in results
                if r.score >= self.score_threshold
            ]
            
            # Build context string
            context = self._build_context(filtered_results)
            
            query_result = QueryResult(
                query=query,
                results=filtered_results,
                context=context
            )
            
            tracer.end_span(span, status=SpanStatus.SUCCESS, output_data={
                "result_count": len(filtered_results),
                "context_length": len(context),
                "top_scores": [r.score for r in filtered_results[:3]]
            })
            return query_result
            
        except Exception as e:
            tracer.end_span(span, SpanStatus.ERROR, error=str(e))
            raise
    
    def _build_context(self, results: list[SearchResult]) -> str:
        """Build context string from search results."""
        if not results:
            return ""
        
        context_parts = []
        for i, result in enumerate(results, 1):
            source = result.metadata.get("source", "unknown")
            context_parts.append(
                f"[Source {i}: {source}]\n{result.content}"
            )
        
        return "\n\n---\n\n".join(context_parts)
    
    async def query_with_rerank(
        self,
        query: str,
        top_k: int | None = None,
        rerank_top_k: int = 3
    ) -> QueryResult:
        """Query with simple reranking based on keyword overlap."""
        from tracing.tracer import Tracer
        from tracing.models import SpanType, SpanStatus
        
        tracer = Tracer.instance()
        span = tracer.start_span(
            SpanType.RETRIEVAL,
            name="rag_query_rerank",
            input_data={"query": query[:200], "top_k": top_k, "rerank_top_k": rerank_top_k}
        )
        
        try:
            # Get more results initially
            fetch_k = (top_k or self.default_top_k) * 2
            results = await self.store.search(query=query, top_k=fetch_k)
            
            # Simple keyword-based reranking
            query_words = set(query.lower().split())
            scored_results = []
            
            for result in results:
                content_words = set(result.content.lower().split())
                overlap = len(query_words & content_words)
                combined_score = result.score + (overlap * 0.1)
                scored_results.append((combined_score, result))
            
            # Sort by combined score and take top results
            scored_results.sort(key=lambda x: x[0], reverse=True)
            reranked = [r for _, r in scored_results[:rerank_top_k]]
            
            context = self._build_context(reranked)
            
            query_result = QueryResult(
                query=query,
                results=reranked,
                context=context
            )
            
            tracer.end_span(span, status=SpanStatus.SUCCESS, output_data={
                "result_count": len(reranked),
                "reranked": True
            })
            return query_result
            
        except Exception as e:
            tracer.end_span(span, SpanStatus.ERROR, error=str(e))
            raise
