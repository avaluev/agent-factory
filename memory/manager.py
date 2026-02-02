"""Unified memory manager."""

from dataclasses import dataclass
from typing import Any

from memory.short_term import ShortTermMemory
from memory.long_term import LongTermMemory
from memory.episodic import EpisodicMemory


@dataclass
class MemoryContext:
    """Combined memory context for agent use."""
    conversation: str
    relevant_facts: list[dict[str, Any]]
    similar_episodes: list[dict[str, Any]]


class MemoryManager:
    """Unified interface for all memory systems."""
    
    _instance: "MemoryManager | None" = None
    
    def __init__(
        self,
        short_term: ShortTermMemory | None = None,
        long_term: LongTermMemory | None = None,
        episodic: EpisodicMemory | None = None
    ):
        self.short_term = short_term or ShortTermMemory()
        self.long_term = long_term or LongTermMemory()
        self.episodic = episodic or EpisodicMemory()
    
    @classmethod
    def instance(cls) -> "MemoryManager":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def reset(cls) -> None:
        """Reset singleton for testing."""
        cls._instance = None
    
    async def get_context(
        self,
        query: str,
        include_conversation: bool = True,
        include_facts: bool = True,
        include_episodes: bool = True
    ) -> MemoryContext:
        """Get combined memory context for a query."""
        from tracing.tracer import Tracer
        from tracing.models import SpanType, SpanStatus
        
        tracer = Tracer.instance()
        span = tracer.start_span(
            SpanType.MEMORY,
            name="memory_get_context",
            input_data={"query": query[:100]}
        )
        
        try:
            # Get conversation history
            conversation = ""
            if include_conversation:
                conversation = self.short_term.get_formatted_context(last_n=10)
            
            # Get relevant facts from long-term memory
            relevant_facts = []
            if include_facts:
                facts = await self.long_term.recall(query, top_k=5)
                relevant_facts = [
                    {
                        "id": f.id,
                        "content": f.content,
                        "category": f.category,
                        "importance": f.importance
                    }
                    for f in facts
                ]
            
            # Get similar past episodes
            similar_episodes = []
            if include_episodes:
                episodes = await self.episodic.recall_similar(query, top_k=3)
                similar_episodes = [
                    {
                        "id": e.id,
                        "task": e.task,
                        "outcome": e.outcome,
                        "result": e.result[:200] if e.result else ""
                    }
                    for e in episodes
                ]
            
            context = MemoryContext(
                conversation=conversation,
                relevant_facts=relevant_facts,
                similar_episodes=similar_episodes
            )
            
            tracer.end_span(span, status=SpanStatus.SUCCESS, output_data={
                "conversation_length": len(conversation),
                "fact_count": len(relevant_facts),
                "episode_count": len(similar_episodes)
            })
            return context
            
        except Exception as e:
            tracer.end_span(span, status=SpanStatus.ERROR, error=str(e))
            raise
    
    def add_message(self, content: str, role: str) -> None:
        """Add message to conversation history."""
        self.short_term.add(content, role)
    
    async def store_fact(
        self,
        content: str,
        category: str = "fact",
        importance: float = 0.5
    ) -> str:
        """Store a fact in long-term memory."""
        return await self.long_term.store(content, category, importance)
    
    async def record_episode(
        self,
        task: str,
        outcome: str,
        steps: list[dict[str, Any]],
        result: str,
        started_at: Any
    ) -> str:
        """Record a task execution episode."""
        return await self.episodic.record(
            task=task,
            outcome=outcome,
            steps=steps,
            result=result,
            started_at=started_at
        )
    
    def format_context_for_prompt(self, context: MemoryContext) -> str:
        """Format memory context for inclusion in prompt."""
        parts = []
        
        if context.conversation:
            parts.append(f"## Recent Conversation\n{context.conversation}")
        
        if context.relevant_facts:
            facts_text = "\n".join(
                f"- [{f['category']}] {f['content']}"
                for f in context.relevant_facts
            )
            parts.append(f"## Relevant Knowledge\n{facts_text}")
        
        if context.similar_episodes:
            episodes_text = "\n".join(
                f"- Task: {e['task']}\n  Outcome: {e['outcome']}\n  Result: {e['result']}"
                for e in context.similar_episodes
            )
            parts.append(f"## Similar Past Tasks\n{episodes_text}")
        
        return "\n\n".join(parts)
