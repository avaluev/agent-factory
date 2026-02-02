"""
Agent Loop — ReAct (Reasoning + Acting) implementation with full tracing.

The agent loop:
1. Receives a task and optional context
2. Constructs messages with available tools
3. Sends to LLM (via model adapter)
4. If LLM returns tool calls → executes them via ToolRegistry → loops
5. If LLM returns text only → that's the final response
6. Enforces max iterations to prevent infinite loops
"""
import logging
import json
from dataclasses import dataclass, field
from typing import Any

from core.models.base import ChatMessage, MessageRole, ModelResponse, ModelAdapter
from core.models.ollama_adapter import OllamaAdapter
from core.models.anthropic_adapter import AnthropicAdapter
from core.tool_registry import ToolRegistry, register_builtin_tools
from core.errors import AgentPlatformError

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 30  # Safety limit
AGENT_SYSTEM_PROMPT = """You are an AI agent running inside the Agent Platform.

You have access to tools that you can call to accomplish tasks. When you need to use a tool, respond with a tool call. When you have enough information to provide a final answer, respond with text only (no tool calls).

IMPORTANT RULES:
1. Always think step by step before acting
2. Use tools when you need external information or capabilities
3. If a tool fails, try an alternative approach or report the error clearly
4. Be concise in your responses — the user sees your final text output
5. When planning complex tasks, break them into smaller steps

Available skills and capabilities will be listed in the context when relevant."""


@dataclass
class AgentSession:
    """Tracks state across an agent's execution."""
    task: str
    messages: list[ChatMessage] = field(default_factory=list)
    iterations: int = 0
    total_cost: float = 0.0
    tool_calls_made: list[dict] = field(default_factory=list)
    status: str = "pending"  # pending | running | completed | failed


class Agent:
    """
    Core ReAct agent.
    
    Usage:
        agent = Agent(model_adapter=OllamaAdapter())
        result = await agent.run("Summarize the files in the current directory")
    """
    
    def __init__(self, model_adapter: ModelAdapter | None = None):
        # Default to local model for cost efficiency
        self.model = model_adapter or OllamaAdapter()
        self.tool_registry = ToolRegistry.instance()
        # Ensure builtin tools are registered
        if not self.tool_registry.list_tools():
            register_builtin_tools()
    
    def _build_system_prompt(self) -> str:
        """Build the system prompt with skill information if available."""
        prompt = AGENT_SYSTEM_PROMPT
        try:
            from skills.registry import SkillRegistry
            skills_snippet = SkillRegistry.instance().get_system_prompt_snippet()
            if skills_snippet:
                prompt += "\n\n" + skills_snippet
        except Exception:
            pass  # Skills not available yet
        return prompt
    
    async def run(self, task: str, context: str | None = None) -> str:
        """
        ReAct loop: Think → Act → Observe.
        Fully traced: one agent_run span wraps N agent_iteration spans,
        each of which wraps the llm_call + any tool_calls.
        """
        from tracing.tracer import Tracer
        from tracing.models import SpanType, SpanStatus

        tracer = Tracer.instance()

        # ── Top-level agent_run span ───────────────────────────────
        run_span = tracer.start_span(
            SpanType.AGENT_RUN,
            name=f"agent_run:{task[:80]}",
            input_data={
                "task": task,
                "context_preview": context[:200] if context else None,
            },
        )

        # Build initial messages
        messages = []
        system_prompt = self._build_system_prompt()
        messages.append(ChatMessage(role=MessageRole.SYSTEM, content=system_prompt))
        if context:
            messages.append(ChatMessage(role=MessageRole.USER, content=f"Context:\n{context}\n\nTask:\n{task}"))
        else:
            messages.append(ChatMessage(role=MessageRole.USER, content=task))

        total_cost = 0.0
        iteration = 0
        result = ""

        try:
            while iteration < MAX_ITERATIONS:
                iteration += 1

                # ── Per-iteration span ─────────────────────────────
                iter_span = tracer.start_span(
                    SpanType.AGENT_ITERATION,
                    name=f"iteration_{iteration}",
                    input_data={"iteration": iteration, "message_count": len(messages)},
                )

                # Get available tools for the LLM
                tools_schema = self.tool_registry.to_llm_tools()

                # LLM call — the adapter itself traces this as an llm_call span
                response = await self.model.chat(messages, tools=tools_schema)
                total_cost += response.cost if hasattr(response, 'cost') else 0.0

                # ── Determine what the LLM decided ─────────────────
                if not response.tool_calls:
                    # LLM produced a final text answer — we're done
                    result = response.content or ""
                    tracer.end_span(iter_span, output_data={
                        "decision": "final_answer",
                        "response_preview": result[:300],
                    })
                    break

                # LLM wants to call tools
                tool_names_called = []
                for tc in response.tool_calls:
                    tool_names_called.append(tc.name)
                    try:
                        # Execute tool — tool_registry traces this as a tool_call span
                        tool_result = await self.tool_registry.execute(tc.name, tc.arguments)
                        # Feed result back as a message
                        messages.append(ChatMessage(role=MessageRole.ASSISTANT, content=response.content or ""))
                        messages.append(ChatMessage(
                            role=MessageRole.TOOL,
                            content=str(tool_result),
                            tool_call_id=tc.id if hasattr(tc, 'id') else tc.name,
                        ))
                    except Exception as e:
                        messages.append(ChatMessage(role=MessageRole.ASSISTANT, content=response.content or ""))
                        messages.append(ChatMessage(
                            role=MessageRole.TOOL,
                            content=f"ERROR: {e}",
                            tool_call_id=tc.id if hasattr(tc, 'id') else tc.name,
                        ))

                tracer.end_span(iter_span, output_data={
                    "decision": "tool_use",
                    "tools_called": tool_names_called,
                    "response_preview": (response.content or "")[:200],
                })

            else:
                # Hit MAX_ITERATIONS
                result = "Agent reached maximum iteration limit without a final answer."

            # ── Close the agent_run span ───────────────────────────
            tracer.end_span(run_span, output_data={
                "result_preview": result[:500],
                "iterations": iteration,
                "total_cost_usd": round(total_cost, 6),
            }, cost_usd=total_cost)

            return result

        except Exception as e:
            tracer.end_span(run_span, status=SpanStatus.ERROR, error=str(e), cost_usd=total_cost)
            raise


async def interactive_session():
    """Run an interactive agent session in the terminal."""
    from rich.console import Console
    from rich.prompt import Prompt
    
    console = Console()
    agent = Agent()
    
    console.print("[bold green]Agent ready. Type your task (or 'quit' to exit):[/]")
    
    while True:
        task = Prompt.ask("\n[bold cyan]You[/]")
        if task.lower() in ('quit', 'exit', 'q'):
            break
        
        console.print("[dim]Thinking...[/]")
        result = await agent.run(task)
        console.print(f"\n[bold green]Agent:[/] {result}")
