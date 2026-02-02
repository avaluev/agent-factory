"""Embedding router with Ollama primary and API fallback."""

import os
import httpx
from typing import Protocol


class EmbeddingProvider(Protocol):
    """Protocol for embedding providers."""
    
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for texts."""
        ...


class OllamaEmbedder:
    """Local Ollama embeddings using nomic-embed-text."""
    
    def __init__(
        self,
        model: str = "nomic-embed-text",
        base_url: str = "http://localhost:11434"
    ):
        self.model = model
        self.base_url = base_url
    
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings via Ollama."""
        embeddings = []
        async with httpx.AsyncClient(timeout=60.0) as client:
            for text in texts:
                response = await client.post(
                    f"{self.base_url}/api/embeddings",
                    json={"model": self.model, "prompt": text}
                )
                response.raise_for_status()
                data = response.json()
                embeddings.append(data["embedding"])
        return embeddings


class OpenAIEmbedder:
    """OpenAI embeddings as fallback."""
    
    def __init__(
        self,
        model: str = "text-embedding-3-small",
        api_key: str | None = None
    ):
        self.model = model
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
    
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings via OpenAI API."""
        if not self.api_key:
            raise ValueError("OpenAI API key not configured")
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/embeddings",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={"model": self.model, "input": texts}
            )
            response.raise_for_status()
            data = response.json()
            return [item["embedding"] for item in data["data"]]


class EmbeddingRouter:
    """Routes embedding requests with fallback support."""
    
    _instance: "EmbeddingRouter | None" = None
    
    def __init__(
        self,
        primary: EmbeddingProvider | None = None,
        fallback: EmbeddingProvider | None = None
    ):
        self.primary = primary or OllamaEmbedder()
        self.fallback = fallback or OpenAIEmbedder()
        self._use_fallback = False
    
    @classmethod
    def instance(cls) -> "EmbeddingRouter":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def reset(cls) -> None:
        """Reset singleton for testing."""
        cls._instance = None
    
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings with tracing and fallback."""
        from tracing.tracer import Tracer
        from tracing.models import SpanType, SpanStatus
        
        tracer = Tracer.instance()
        span = tracer.start_span(
            SpanType.EMBEDDING,
            name="embedding_generation",
            input_data={"text_count": len(texts), "sample": texts[0][:100] if texts else ""}
        )
        
        try:
            if not self._use_fallback:
                try:
                    result = await self.primary.embed(texts)
                    tracer.end_span(span, status=SpanStatus.SUCCESS, output_data={
                        "provider": "ollama",
                        "dimension": len(result[0]) if result else 0
                    })
                    return result
                except Exception as e:
                    # Primary failed, switch to fallback
                    self._use_fallback = True
                    tracer.end_span(span, status=SpanStatus.SUCCESS, output_data={
                        "provider": "ollama",
                        "fallback_triggered": True,
                        "error": str(e)
                    })
            
            # Use fallback
            span2 = tracer.start_span(
                SpanType.EMBEDDING,
                name="embedding_fallback",
                input_data={"text_count": len(texts)}
            )
            try:
                result = await self.fallback.embed(texts)
                tracer.end_span(span2, status=SpanStatus.SUCCESS, output_data={
                    "provider": "openai",
                    "dimension": len(result[0]) if result else 0
                })
                return result
            except Exception as e:
                tracer.end_span(span2, status=SpanStatus.ERROR, error=str(e))
                raise

        except Exception as e:
            if span.status == SpanStatus.PENDING:
                tracer.end_span(span, status=SpanStatus.ERROR, error=str(e))
            raise
