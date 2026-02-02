"""Memory tools for agent use."""

from core.tool_registry import ToolRegistry, ToolSchema


def register_memory_tools() -> None:
    """Register memory tools with the tool registry."""
    registry = ToolRegistry.instance()
    
    # Memory recall tool
    async def handle_memory_recall(query: str, memory_type: str = "all") -> dict:
        """Handle memory recall tool call."""
        from memory.manager import MemoryManager

        manager = MemoryManager.instance()

        context = await manager.get_context(
            query=query,
            include_conversation=True,
            include_facts=memory_type in ["all", "facts"],
            include_episodes=memory_type in ["all", "episodes"]
        )

        return {
            "query": query,
            "conversation_context": context.conversation[:500] if context.conversation else "",
            "relevant_facts": context.relevant_facts,
            "similar_episodes": context.similar_episodes
        }

    registry.register(ToolSchema(
        name="memory_recall",
        description="Recall relevant information from memory. Searches conversation history, stored facts, and past task outcomes.",
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What to search for in memory"
                },
                "memory_type": {
                    "type": "string",
                    "enum": ["all", "facts", "episodes"],
                    "description": "Type of memory to search",
                    "default": "all"
                }
            },
            "required": ["query"]
        },
        handler=handle_memory_recall,
        category="memory",
        cost_tier="free"
    ))
    
    # Memory store tool
    async def handle_memory_store(content: str, category: str = "fact", importance: float = 0.5) -> dict:
        """Handle memory store tool call."""
        from memory.manager import MemoryManager

        manager = MemoryManager.instance()
        memory_id = await manager.store_fact(content, category, importance)

        return {
            "success": True,
            "memory_id": memory_id,
            "category": category,
            "importance": importance
        }

    registry.register(ToolSchema(
        name="memory_store",
        description="Store important information in long-term memory for future reference.",
        parameters={
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The information to remember"
                },
                "category": {
                    "type": "string",
                    "enum": ["fact", "preference", "learned", "context"],
                    "description": "Category of the memory",
                    "default": "fact"
                },
                "importance": {
                    "type": "number",
                    "description": "Importance level from 0 to 1",
                    "default": 0.5
                }
            },
            "required": ["content"]
        },
        handler=handle_memory_store,
        category="memory",
        cost_tier="free"
    ))
