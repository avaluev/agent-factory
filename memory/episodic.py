"""Episodic memory for task execution history."""

import os
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
import sqlite3
import json


@dataclass
class Episode:
    """Single episode (task execution record)."""
    id: str
    task: str
    outcome: str  # "success", "failure", "partial"
    steps: list[dict[str, Any]]
    result: str
    started_at: datetime
    completed_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)


class EpisodicMemory:
    """Memory for past task executions and outcomes."""
    
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or os.getenv(
            "EPISODIC_DB_PATH",
            str(Path.home() / ".agent-platform" / "episodic_memory.db")
        )
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self) -> None:
        """Initialize SQLite database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS episodes (
                    id TEXT PRIMARY KEY,
                    task TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    steps TEXT NOT NULL,
                    result TEXT,
                    started_at TEXT NOT NULL,
                    completed_at TEXT NOT NULL,
                    metadata TEXT DEFAULT '{}'
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_outcome ON episodes(outcome)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_completed ON episodes(completed_at DESC)
            """)
    
    async def record(
        self,
        task: str,
        outcome: str,
        steps: list[dict[str, Any]],
        result: str,
        started_at: datetime,
        metadata: dict[str, Any] | None = None
    ) -> str:
        """Record a task execution episode."""
        from tracing.tracer import Tracer
        from tracing.models import SpanType, SpanStatus
        import hashlib
        
        tracer = Tracer.instance()
        span = tracer.start_span(
            SpanType.MEMORY,
            name="episodic_record",
            input_data={"task": task[:100], "outcome": outcome, "step_count": len(steps)}
        )
        
        try:
            episode_id = hashlib.sha256(
                f"{task}{started_at.isoformat()}".encode()
            ).hexdigest()[:16]
            
            completed_at = datetime.utcnow()
            
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO episodes
                    (id, task, outcome, steps, result, started_at, completed_at, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    episode_id,
                    task,
                    outcome,
                    json.dumps(steps),
                    result,
                    started_at.isoformat(),
                    completed_at.isoformat(),
                    json.dumps(metadata or {})
                ))
            
            tracer.end_span(span, status=SpanStatus.SUCCESS, output_data={"id": episode_id})
            return episode_id
            
        except Exception as e:
            tracer.end_span(span, status=SpanStatus.ERROR, error=str(e))
            raise
    
    async def recall_similar(
        self,
        task: str,
        top_k: int = 3,
        outcome_filter: str | None = None
    ) -> list[Episode]:
        """Recall similar past episodes."""
        from tracing.tracer import Tracer
        from tracing.models import SpanType, SpanStatus
        
        tracer = Tracer.instance()
        span = tracer.start_span(
            SpanType.MEMORY,
            name="episodic_recall",
            input_data={"task": task[:100], "top_k": top_k}
        )
        
        try:
            # Try semantic search first
            episodes = await self._semantic_search(task, top_k, outcome_filter)
            
            if not episodes:
                # Fallback to keyword search
                episodes = self._keyword_search(task, top_k, outcome_filter)
            
            tracer.end_span(span, status=SpanStatus.SUCCESS, output_data={"count": len(episodes)})
            return episodes
            
        except Exception as e:
            tracer.end_span(span, status=SpanStatus.ERROR, error=str(e))
            raise
    
    async def _semantic_search(
        self,
        task: str,
        top_k: int,
        outcome_filter: str | None
    ) -> list[Episode]:
        """Search using vector similarity."""
        try:
            from rag.store.chroma_store import ChromaStore
            store = ChromaStore.instance()
            
            filter_meta = {"type": "episode"}
            if outcome_filter:
                filter_meta["outcome"] = outcome_filter
            
            results = await store.search(
                query=task,
                top_k=top_k,
                filter_metadata=filter_meta
            )
            
            episode_ids = [
                r.metadata.get("episode_id")
                for r in results
                if r.metadata.get("episode_id")
            ]
            
            return self._get_episodes_by_ids(episode_ids)
        except Exception:
            return []
    
    def _keyword_search(
        self,
        task: str,
        top_k: int,
        outcome_filter: str | None
    ) -> list[Episode]:
        """Fallback keyword search."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            if outcome_filter:
                cursor = conn.execute("""
                    SELECT * FROM episodes
                    WHERE outcome = ? AND task LIKE ?
                    ORDER BY completed_at DESC
                    LIMIT ?
                """, (outcome_filter, f"%{task}%", top_k))
            else:
                cursor = conn.execute("""
                    SELECT * FROM episodes
                    WHERE task LIKE ?
                    ORDER BY completed_at DESC
                    LIMIT ?
                """, (f"%{task}%", top_k))
            
            return [self._row_to_episode(row) for row in cursor]
    
    def _get_episodes_by_ids(self, ids: list[str]) -> list[Episode]:
        """Get episodes by IDs."""
        if not ids:
            return []
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            placeholders = ",".join("?" * len(ids))
            cursor = conn.execute(
                f"SELECT * FROM episodes WHERE id IN ({placeholders})",
                ids
            )
            return [self._row_to_episode(row) for row in cursor]
    
    def _row_to_episode(self, row: sqlite3.Row) -> Episode:
        """Convert database row to Episode."""
        return Episode(
            id=row["id"],
            task=row["task"],
            outcome=row["outcome"],
            steps=json.loads(row["steps"]),
            result=row["result"],
            started_at=datetime.fromisoformat(row["started_at"]),
            completed_at=datetime.fromisoformat(row["completed_at"]),
            metadata=json.loads(row["metadata"])
        )
    
    def get_recent(self, limit: int = 10) -> list[Episode]:
        """Get recent episodes."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM episodes
                ORDER BY completed_at DESC
                LIMIT ?
            """, (limit,))
            return [self._row_to_episode(row) for row in cursor]
    
    def get_success_rate(self, task_pattern: str | None = None) -> dict[str, Any]:
        """Get success rate statistics."""
        with sqlite3.connect(self.db_path) as conn:
            if task_pattern:
                cursor = conn.execute("""
                    SELECT outcome, COUNT(*) as count
                    FROM episodes
                    WHERE task LIKE ?
                    GROUP BY outcome
                """, (f"%{task_pattern}%",))
            else:
                cursor = conn.execute("""
                    SELECT outcome, COUNT(*) as count
                    FROM episodes
                    GROUP BY outcome
                """)
            
            stats = {row[0]: row[1] for row in cursor}
            total = sum(stats.values())
            
            return {
                "total": total,
                "success": stats.get("success", 0),
                "failure": stats.get("failure", 0),
                "partial": stats.get("partial", 0),
                "success_rate": stats.get("success", 0) / total if total > 0 else 0
            }
