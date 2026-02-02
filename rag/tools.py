"""RAG tools for agent use."""

from core.tool_registry import ToolRegistry, ToolSchema


def register_rag_tools() -> None:
    """Register RAG tools with the tool registry."""
    registry = ToolRegistry.instance()
    
    # RAG Query tool
    registry.register(
        schema=ToolSchema(
            name="rag_query",
            description="Search the knowledge base for relevant information. Use this to find context for answering questions.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query to find relevant documents"
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of results to return (default: 5)",
                        "default": 5
                    }
                },
                "required": ["query"]
            }
        ),
        handler=_handle_rag_query
    )
    
    # RAG Ingest tool
    registry.register(
        schema=ToolSchema(
            name="rag_ingest",
            description="Add documents to the knowledge base. Can ingest files or raw text.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to file or directory to ingest"
                    },
                    "text": {
                        "type": "string",
                        "description": "Raw text to ingest (alternative to path)"
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": "For directories, whether to process recursively",
                        "default": True
                    }
                }
            }
        ),
        handler=_handle_rag_ingest
    )


async def _handle_rag_query(params: dict) -> dict:
    """Handle RAG query tool call."""
    from rag.retrieval.query_engine import QueryEngine
    
    query = params.get("query", "")
    top_k = params.get("top_k", 5)
    
    if not query:
        return {"error": "Query is required"}
    
    engine = QueryEngine()
    result = await engine.query(query=query, top_k=top_k)
    
    return {
        "query": result.query,
        "result_count": len(result.results),
        "context": result.context,
        "sources": [
            {
                "id": r.id,
                "score": r.score,
                "source": r.metadata.get("source", "unknown")
            }
            for r in result.results
        ]
    }


async def _handle_rag_ingest(params: dict) -> dict:
    """Handle RAG ingest tool call."""
    from pathlib import Path
    from rag.ingestion.pipeline import IngestPipeline
    
    path = params.get("path")
    text = params.get("text")
    recursive = params.get("recursive", True)
    
    if not path and not text:
        return {"error": "Either 'path' or 'text' is required"}
    
    pipeline = IngestPipeline()
    
    if text:
        result = await pipeline.ingest_text(text)
    elif Path(path).is_file():
        result = await pipeline.ingest_file(path)
    elif Path(path).is_dir():
        result = await pipeline.ingest_directory(path, recursive=recursive)
    else:
        return {"error": f"Path not found: {path}"}
    
    return {
        "success": True,
        "documents_processed": result.total_documents,
        "chunks_created": result.total_chunks,
        "chunk_ids": result.chunk_ids[:10]  # Return first 10 IDs
    }
