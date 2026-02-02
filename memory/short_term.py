"""Short-term memory for conversation context."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from collections import deque


@dataclass
class MemoryEntry:
    """Single memory entry."""
    content: str
    role: str  # "user", "assistant", "system", "tool"
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)


class ShortTermMemory:
    """In-memory conversation buffer with sliding window."""
    
    def __init__(self, max_entries: int = 50, max_tokens: int = 8000):
        self.max_entries = max_entries
        self.max_tokens = max_tokens
        self._entries: deque[MemoryEntry] = deque(maxlen=max_entries)
        self._token_count = 0
    
    def add(
        self,
        content: str,
        role: str,
        metadata: dict[str, Any] | None = None
    ) -> None:
        """Add entry to short-term memory."""
        from tracing.tracer import Tracer
        from tracing.models import SpanType, SpanStatus
        
        tracer = Tracer.instance()
        span = tracer.start_span(
            SpanType.MEMORY,
            name="stm_add",
            input_data={"role": role, "content_length": len(content)}
        )
        
        try:
            entry = MemoryEntry(
                content=content,
                role=role,
                metadata=metadata or {}
            )
            
            # Estimate tokens (rough: 4 chars per token)
            entry_tokens = len(content) // 4
            
            # Evict old entries if over token limit
            while self._token_count + entry_tokens > self.max_tokens and self._entries:
                removed = self._entries.popleft()
                self._token_count -= len(removed.content) // 4
            
            self._entries.append(entry)
            self._token_count += entry_tokens
            
            tracer.end_span(span, status=SpanStatus.SUCCESS, output_data={
                "entry_count": len(self._entries),
                "token_count": self._token_count
            })
            
        except Exception as e:
            tracer.end_span(span, status=SpanStatus.ERROR, error=str(e))
            raise
    
    def get_context(self, last_n: int | None = None) -> list[dict[str, Any]]:
        """Get conversation context as list of messages."""
        entries = list(self._entries)
        if last_n:
            entries = entries[-last_n:]
        
        return [
            {
                "role": e.role,
                "content": e.content,
                "timestamp": e.timestamp.isoformat()
            }
            for e in entries
        ]
    
    def get_formatted_context(self, last_n: int | None = None) -> str:
        """Get context formatted as string."""
        entries = list(self._entries)
        if last_n:
            entries = entries[-last_n:]
        
        lines = []
        for entry in entries:
            prefix = entry.role.upper()
            lines.append(f"[{prefix}]: {entry.content}")
        
        return "\n".join(lines)
    
    def clear(self) -> None:
        """Clear all entries."""
        self._entries.clear()
        self._token_count = 0
    
    def __len__(self) -> int:
        return len(self._entries)
