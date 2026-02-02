"""
Tool Registry — Central hub for all agent capabilities.

Tools are registered with:
- name: unique identifier
- description: what it does (shown to LLM for decision making)
- parameters: JSON Schema defining inputs
- handler: async function that executes the tool
- cost_tier: "free" | "cheap" | "premium" (for routing decisions)
"""
import asyncio
import json
import logging
import time
from typing import Any, Callable, Awaitable
from dataclasses import dataclass, field
from datetime import datetime

from core.errors import ToolExecutionError

logger = logging.getLogger(__name__)


@dataclass
class ToolSchema:
    """JSON Schema-compatible tool definition."""
    name: str
    description: str
    parameters: dict  # JSON Schema for input validation
    handler: Callable[..., Awaitable[Any]]
    cost_tier: str = "free"  # free | cheap | premium
    category: str = "general"  # general | rag | memory | skill | mcp | workflow
    
    def to_llm_format(self) -> dict:
        """Convert to the format LLMs expect for tool/function calling."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            }
        }


class ToolRegistry:
    """
    Singleton registry for all platform tools.
    
    Usage:
        registry = ToolRegistry.instance()
        registry.register(tool_schema)
        result = await registry.execute("tool_name", {"param": "value"})
    """
    _instance: "ToolRegistry | None" = None
    
    def __init__(self):
        self._tools: dict[str, ToolSchema] = {}
        self._log: list[dict] = []
    
    @classmethod
    def instance(cls) -> "ToolRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def register(self, tool: ToolSchema) -> None:
        """Register a tool. Raises if name already exists."""
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' already registered")
        self._tools[tool.name] = tool
        logger.info(f"Registered tool: {tool.name} (category={tool.category}, cost={tool.cost_tier})")
    
    def unregister(self, name: str) -> None:
        """Remove a tool by name."""
        self._tools.pop(name, None)
    
    def get(self, name: str) -> ToolSchema | None:
        """Get tool by name."""
        return self._tools.get(name)
    
    def list_tools(self, category: str | None = None) -> list[ToolSchema]:
        """List all tools, optionally filtered by category."""
        tools = list(self._tools.values())
        if category:
            tools = [t for t in tools if t.category == category]
        return tools
    
    def to_llm_tools(self, categories: list[str] | None = None) -> list[dict]:
        """
        Export all tools in LLM function-calling format.
        Use this to populate the `tools` parameter in API calls.
        """
        tools = self._tools.values()
        if categories:
            tools = [t for t in tools if t.category in categories]
        return [t.to_llm_format() for t in tools]
    
    async def execute(self, tool_name: str, params: dict) -> Any:
        """Execute a tool by name with given parameters, traced."""
        from tracing.tracer import Tracer
        from tracing.models import SpanType, SpanStatus

        if tool_name not in self._tools:
            raise ToolExecutionError(tool_name, f"Tool '{tool_name}' not found")

        tool = self._tools[tool_name]

        # Validate required params
        required = tool.parameters.get("required", [])
        missing = [p for p in required if p not in params]
        if missing:
            raise ToolExecutionError(tool_name, f"Missing params: {missing}")

        tracer = Tracer.instance()
        span = tracer.start_span(
            SpanType.TOOL_CALL,
            name=tool_name,
            input_data={"tool": tool_name, "params": params},
        )

        try:
            t0 = time.monotonic()
            result = await tool.handler(**params) if asyncio.iscoroutinefunction(tool.handler) else tool.handler(**params)
            elapsed = time.monotonic() - t0

            # Log execution
            self._log.append({
                "tool": tool_name,
                "params": params,
                "result_preview": str(result)[:200],
                "duration_ms": round(elapsed * 1000, 1),
            })

            tracer.end_span(span, output_data={
                "result_preview": str(result)[:500],
                "duration_ms": round(elapsed * 1000, 1),
            })
            return result

        except Exception as e:
            tracer.end_span(span, status=SpanStatus.ERROR, error=str(e))
            raise ToolExecutionError(tool_name, str(e)) from e
    
    def get_execution_log(self) -> list[dict]:
        """Get full execution history (for debugging/cost analysis)."""
        return self._log.copy()


# --- Built-in utility tools registered at startup ---

def register_builtin_tools():
    """Register core utility tools that are always available."""
    registry = ToolRegistry.instance()
    
    # --- read_file tool ---
    async def read_file(path: str) -> str:
        """Read a local file and return its contents."""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            return f"ERROR: File not found: {path}"
        except Exception as e:
            return f"ERROR: {e}"
    
    registry.register(ToolSchema(
        name="read_file",
        description="Read a local file and return its text contents. Use for .txt, .md, .csv, .py files.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute or relative path to the file"}
            },
            "required": ["path"]
        },
        handler=read_file,
        cost_tier="free",
        category="general"
    ))
    
    # --- list_directory tool ---
    async def list_directory(path: str = ".", max_depth: int = 2) -> str:
        """List files in a directory."""
        import os
        result = []
        for root, dirs, files in os.walk(path):
            depth = root.replace(path, '').count(os.sep)
            if depth >= max_depth:
                dirs.clear()
                continue
            indent = "  " * depth
            result.append(f"{indent}{os.path.basename(root)}/")
            subindent = "  " * (depth + 1)
            for file in files:
                result.append(f"{subindent}{file}")
        return "\n".join(result)
    
    registry.register(ToolSchema(
        name="list_directory",
        description="List files and folders in a directory. Use to explore project structure.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path", "default": "."},
                "max_depth": {"type": "integer", "description": "Max depth to traverse", "default": 2}
            },
            "required": []
        },
        handler=list_directory,
        cost_tier="free",
        category="general"
    ))
    
    # --- get_timestamp tool ---
    async def get_timestamp() -> str:
        return datetime.now().isoformat()
    
    registry.register(ToolSchema(
        name="get_timestamp",
        description="Get the current timestamp in ISO format.",
        parameters={"type": "object", "properties": {}, "required": []},
        handler=get_timestamp,
        cost_tier="free",
        category="general"
    ))
