"""
Trace Store — SQLite persistence and query interface.

All spans are written here. Queries support:
- Full trace replay (all spans for a trace_id, in order)
- Recent traces summary
- Filter by span type
- LLM cost aggregation
- Error-only view
"""
import os
import json
import sqlite3
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

TRACE_DB_PATH = os.environ.get("TRACE_DB_PATH", "./data/traces.db")


class TraceStore:
    def __init__(self, db_path: str | None = None):
        self._db_path = db_path or TRACE_DB_PATH
        os.makedirs(os.path.dirname(self._db_path) or ".", exist_ok=True)
        self._init_schema()

    # ── connection ─────────────────────────────────────────────────
    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self._db_path)
        c.row_factory = sqlite3.Row
        return c

    def _init_schema(self):
        conn = self._conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS traces (
                id                TEXT PRIMARY KEY,
                parent_id         TEXT,
                trace_id          TEXT,
                span_type         TEXT    NOT NULL,
                name              TEXT    NOT NULL,
                status            TEXT    NOT NULL DEFAULT 'pending',
                started_at        TEXT,
                ended_at          TEXT,
                duration_ms       REAL    DEFAULT 0,
                input_data        TEXT    DEFAULT '{}',
                output_data       TEXT    DEFAULT '{}',
                error             TEXT,
                model             TEXT,
                provider          TEXT,
                input_tokens      INTEGER DEFAULT 0,
                output_tokens     INTEGER DEFAULT 0,
                cost_usd          REAL    DEFAULT 0,
                decision_reasoning TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_trace_id      ON traces(trace_id);
            CREATE INDEX IF NOT EXISTS idx_span_type     ON traces(span_type);
            CREATE INDEX IF NOT EXISTS idx_started_at    ON traces(started_at);
            CREATE INDEX IF NOT EXISTS idx_parent_id     ON traces(parent_id);
            CREATE INDEX IF NOT EXISTS idx_status        ON traces(status);
        """)
        conn.commit()
        conn.close()

    # ── write ──────────────────────────────────────────────────────
    def save(self, span) -> None:
        """Persist a TraceSpan."""
        conn = self._conn()
        conn.execute("""
            INSERT OR REPLACE INTO traces (
                id, parent_id, trace_id, span_type, name, status,
                started_at, ended_at, duration_ms,
                input_data, output_data, error,
                model, provider, input_tokens, output_tokens, cost_usd,
                decision_reasoning
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            span.id, span.parent_id, span.trace_id,
            span.span_type.value, span.name, span.status.value,
            span.started_at, span.ended_at, span.duration_ms,
            json.dumps(span.input_data),
            json.dumps(span.output_data),
            span.error,
            span.model, span.provider,
            span.input_tokens, span.output_tokens, span.cost_usd,
            span.decision_reasoning,
        ))
        conn.commit()
        conn.close()

    # ── read ───────────────────────────────────────────────────────
    def get_trace(self, trace_id: str) -> list[dict]:
        """All spans for one trace, ordered by start time."""
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM traces WHERE trace_id = ? ORDER BY started_at",
            (trace_id,)
        ).fetchall()
        conn.close()
        return [self._parse(r) for r in rows]

    def get_recent_traces(self, limit: int = 10) -> list[dict]:
        """Summary row per trace_id, most recent first."""
        conn = self._conn()
        rows = conn.execute("""
            SELECT
                trace_id,
                COUNT(*)                          AS span_count,
                MIN(started_at)                   AS started_at,
                MAX(ended_at)                     AS ended_at,
                ROUND(SUM(cost_usd), 6)           AS total_cost,
                GROUP_CONCAT(DISTINCT span_type)  AS span_types,
                SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) AS error_count
            FROM traces
            WHERE trace_id IS NOT NULL
            GROUP BY trace_id
            ORDER BY MIN(started_at) DESC
            LIMIT ?
        """, (limit,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_spans_by_type(self, span_type: str, limit: int = 20) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM traces WHERE span_type = ? ORDER BY started_at DESC LIMIT ?",
            (span_type, limit)
        ).fetchall()
        conn.close()
        return [self._parse(r) for r in rows]

    def get_errors(self, limit: int = 20) -> list[dict]:
        """All spans that ended in error, most recent first."""
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM traces WHERE status = 'error' ORDER BY started_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
        conn.close()
        return [self._parse(r) for r in rows]

    def get_llm_summary(self, days: int = 7) -> dict:
        """Aggregate stats for all LLM calls in the last N days."""
        conn = self._conn()
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        # Per-provider breakdown
        rows = conn.execute("""
            SELECT
                provider,
                COUNT(*)                     AS calls,
                ROUND(SUM(cost_usd), 6)      AS cost,
                ROUND(AVG(duration_ms), 1)   AS avg_latency_ms,
                SUM(input_tokens)            AS input_tokens,
                SUM(output_tokens)           AS output_tokens,
                SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) AS errors
            FROM traces
            WHERE span_type = 'llm_call' AND started_at > ?
            GROUP BY provider
            ORDER BY cost DESC
        """, (cutoff,)).fetchall()
        conn.close()

        return {
            "period_days": days,
            "by_provider": [dict(r) for r in rows],
            "total_cost": sum(r["cost"] or 0 for r in rows),
            "total_calls": sum(r["calls"] or 0 for r in rows),
        }

    # ── helpers ────────────────────────────────────────────────────
    @staticmethod
    def _parse(row) -> dict:
        d = dict(row)
        for field in ("input_data", "output_data"):
            if d.get(field):
                try:
                    d[field] = json.loads(d[field])
                except (json.JSONDecodeError, TypeError):
                    pass
        return d
