"""Long-term memory with vector storage."""

import os
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import sqlite3


@dataclass
class LongTermEntry:
    """Long-term memory entry."""
    id: str
    content: str
    category: str  # "fact", "preference", "learned", "context"
    importance: float = 0.5  # 0-1 scale
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_accessed: datetime = field(default_factory=datetime.utcnow)
    access_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class LongTermMemory:
    """Persistent long-term memory with semantic search."""
    
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or os.getenv(
            "LTM_DB_PATH",
            str(Path.home() / ".agent-platform" / "long_term_memory.db")
        )
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self) -> None:
        """Initialize SQLite database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    category TEXT NOT NULL,
                    importance REAL DEFAULT 0.5,
                    created_at TEXT NOT NULL,
                    last_accessed TEXT NOT NULL,
                    access_count INTEGER DEFAULT 0,
                    metadata TEXT DEFAULT '{}'
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_category ON memories(category)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_importance ON memories(importance DESC)
            """)
    
    async def store(
        self,
        content: str,
        category: str = "fact",
        importance: float = 0.5,
        metadata: dict[str, Any] | None = None
    ) -> str:
        """Store a memory entry."""
        from tracing.tracer import Tracer
        from tracing.models import SpanType, SpanStatus
        import hashlib
        import json
        
        tracer = Tracer.instance()
        span = tracer.start_span(
            SpanType.MEMORY_OP,
            name="ltm_store",
            input_data={"category": category, "importance": importance}
        )
        
        try:
            memory_id = hashlib.sha256(
                f"{content}{datetime.utcnow().isoformat()}".encode()
            ).hexdigest()[:16]
            
            now = datetime.utcnow().isoformat()
            
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO memories
                    (id, content, category, importance, created_at, last_accessed, access_count, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, 0, ?)
                """, (
                    memory_id,
                    content,
                    category,
                    importance,
                    now,
                    now,
                    json.dumps(metadata or {})
                ))
            
            # Also store in vector DB for semantic search
            await self._store_embedding(memory_id, content, category)
            
            tracer.end_span(span, status=SpanStatus.SUCCESS, output_data={"id": memory_id})
            return memory_id
            
        except Exception as e:
            tracer.end_span(span, status=SpanStatus.ERROR, error=str(e))
            raise
    
    async def _store_embedding(self, memory_id: str, content: str, category: str) -> None:
        """Store embedding for semantic search."""
        try:
            from rag.store.chroma_store import ChromaStore
            store = ChromaStore.instance()
            await store.add(
                documents=[content],
                metadatas=[{"memory_id": memory_id, "category": category, "type": "ltm"}],
                ids=[f"ltm_{memory_id}"]
            )
        except Exception:
            # Vector storage is optional enhancement
            pass
    
    async def recall(
        self,
        query: str,
        category: str | None = None,
        top_k: int = 5
    ) -> list[LongTermEntry]:
        """Recall memories by semantic search."""
        from tracing.tracer import Tracer
        from tracing.models import SpanType, SpanStatus
        import json
        
        tracer = Tracer.instance()
        span = tracer.start_span(
            SpanType.MEMORY_OP,
            name="ltm_recall",
            input_data={"query": query[:100], "category": category, "top_k": top_k}
        )
        
        try:
            # Try semantic search first
            memory_ids = await self._semantic_search(query, category, top_k)
            
            if not memory_ids:
                # Fallback to keyword search
                memory_ids = self._keyword_search(query, category, top_k)
            
            # Fetch full entries
            entries = []
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                placeholders = ",".join("?" * len(memory_ids))
                cursor = conn.execute(f"""
                    SELECT * FROM memories WHERE id IN ({placeholders})
                """, memory_ids)
                
                for row in cursor:
                    entries.append(LongTermEntry(
                        id=row["id"],
                        content=row["content"],
                        category=row["category"],
                        importance=row["importance"],
                        created_at=datetime.fromisoformat(row["created_at"]),
                        last_accessed=datetime.fromisoformat(row["last_accessed"]),
                        access_count=row["access_count"],
                        metadata=json.loads(row["metadata"])
                    ))
                    
                    # Update access stats
                    conn.execute("""
                        UPDATE memories SET 
                            last_accessed = ?,
                            access_count = access_count + 1
                        WHERE id = ?
                    """, (datetime.utcnow().isoformat(), row["id"]))
            
            tracer.end_span(span, status=SpanStatus.SUCCESS, output_data={"count": len(entries)})
            return entries
            
        except Exception as e:
            tracer.end_span(span, status=SpanStatus.ERROR, error=str(e))
            raise
    
    async def _semantic_search(
        self,
        query: str,
        category: str | None,
        top_k: int
    ) -> list[str]:
        """Search using vector similarity."""
        try:
            from rag.store.chroma_store import ChromaStore
            store = ChromaStore.instance()
            
            filter_meta = {"type": "ltm"}
            if category:
                filter_meta["category"] = category
            
            results = await store.search(
                query=query,
                top_k=top_k,
                filter_metadata=filter_meta
            )
            
            return [r.metadata.get("memory_id") for r in results if r.metadata.get("memory_id")]
        except Exception:
            return []
    
    def _keyword_search(
        self,
        query: str,
        category: str | None,
        top_k: int
    ) -> list[str]:
        """Fallback keyword search."""
        with sqlite3.connect(self.db_path) as conn:
            if category:
                cursor = conn.execute("""
                    SELECT id FROM memories
                    WHERE category = ? AND content LIKE ?
                    ORDER BY importance DESC, access_count DESC
                    LIMIT ?
                """, (category, f"%{query}%", top_k))
            else:
                cursor = conn.execute("""
                    SELECT id FROM memories
                    WHERE content LIKE ?
                    ORDER BY importance DESC, access_count DESC
                    LIMIT ?
                """, (f"%{query}%", top_k))
            
            return [row[0] for row in cursor]
    
    def get_by_category(self, category: str, limit: int = 10) -> list[LongTermEntry]:
        """Get memories by category."""
        import json
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM memories
                WHERE category = ?
                ORDER BY importance DESC, last_accessed DESC
                LIMIT ?
            """, (category, limit))
            
            return [
                LongTermEntry(
                    id=row["id"],
                    content=row["content"],
                    category=row["category"],
                    importance=row["importance"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                    last_accessed=datetime.fromisoformat(row["last_accessed"]),
                    access_count=row["access_count"],
                    metadata=json.loads(row["metadata"])
                )
                for row in cursor
            ]
    
    def forget(self, memory_id: str) -> bool:
        """Remove a memory entry."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            return cursor.rowcount > 0
