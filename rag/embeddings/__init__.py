"""Embedding providers with routing and fallback."""

from rag.embeddings.embedding_router import (
    EmbeddingProvider,
    EmbeddingRouter,
    OllamaEmbedder,
    OpenAIEmbedder,
)

__all__ = [
    "EmbeddingProvider",
    "EmbeddingRouter",
    "OllamaEmbedder",
    "OpenAIEmbedder",
]
