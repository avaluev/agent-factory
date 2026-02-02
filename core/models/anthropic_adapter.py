"""Anthropic Claude adapter with tracing."""
import os
import time
import logging
import anthropic
from core.models.base import ModelAdapter, ChatMessage, ModelResponse, ToolCall, MessageRole
from core.errors import ModelProviderError

logger = logging.getLogger(__name__)

# Cost per 1M tokens (as of Feb 2025)
PRICING = {
    "claude-sonnet-4-5-20250929": {"input": 3.00, "output": 15.00},
    "claude-haiku-4-5-20251001": {"input": 0.25, "output": 1.25},
}


class AnthropicAdapter(ModelAdapter):
    def __init__(self, model: str = "claude-haiku-4-5-20251001", **kwargs):
        api_key = kwargs.get("api_key") or os.environ.get("ANTHROPIC_API_KEY")
        super().__init__(api_key=api_key)
        self._model = model
        self._client = anthropic.Anthropic(api_key=api_key)
    
    @property
    def provider_name(self) -> str:
        return "anthropic"
    
    @property
    def model_name(self) -> str:
        return self._model
    
    def _format_messages(self, messages: list) -> list[dict]:
        """Convert to Anthropic format."""
        converted = []
        for msg in messages:
            role = msg.role if isinstance(msg.role, str) else msg.role.value
            if role == "system":
                continue  # System messages handled separately
            elif role == "tool":
                converted.append({
                    "role": "user",
                    "content": [{"type": "tool_result", "tool_use_id": msg.tool_call_id or "unknown", "content": msg.content}]
                })
            elif role == "assistant" and hasattr(msg, 'tool_calls') and msg.tool_calls:
                # Assistant message with tool calls - format with tool_use blocks
                content = []
                if msg.content:
                    content.append({"type": "text", "text": msg.content})
                for tc in msg.tool_calls:
                    content.append({
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.name,
                        "input": tc.arguments
                    })
                converted.append({"role": "assistant", "content": content})
            else:
                converted.append({"role": role, "content": msg.content})
        return converted
    
    async def chat(self, messages: list, tools: list | None = None, temperature: float = 0.7, max_tokens: int = 4096) -> ModelResponse:
        """Call Anthropic API. Every call is traced as an llm_call span with full I/O."""
        from tracing.tracer import Tracer
        from tracing.models import SpanType, SpanStatus

        tracer = Tracer.instance()
        span = tracer.start_span(
            SpanType.LLM_CALL,
            name=f"anthropic:{self._model}",
            input_data={
                "model": self._model,
                "message_count": len(messages),
                "has_tools": bool(tools),
                "temperature": temperature,
                "max_tokens": max_tokens,
                "last_user_message": next(
                    (m.content[:500] if hasattr(m, 'content') else str(m)[:500]
                     for m in reversed(messages)
                     if (m.role if isinstance(m.role, str) else m.role.value) == "user"),
                    None
                ),
            },
            model=self._model,
            provider="anthropic",
        )

        try:
            t0 = time.monotonic()

            # Get system message
            system = next(
                (m.content for m in messages if (m.role if isinstance(m.role, str) else m.role.value) == "system"),
                None
            )
            anthropic_messages = self._format_messages(messages)

            kwargs = {
                "model": self._model,
                "max_tokens": max_tokens,
                "messages": anthropic_messages,
                "temperature": temperature,
            }
            if system:
                kwargs["system"] = system
            if tools:
                kwargs["tools"] = [
                    {
                        "name": t["function"]["name"],
                        "description": t["function"]["description"],
                        "input_schema": t["function"]["parameters"],
                    }
                    for t in tools
                ]

            response = self._client.messages.create(**kwargs)
            elapsed_ms = (time.monotonic() - t0) * 1000

            # Parse response
            text_content = ""
            tool_calls = []
            for block in response.content:
                if block.type == "text":
                    text_content += block.text
                elif block.type == "tool_use":
                    tool_calls.append(ToolCall(
                        id=block.id,
                        name=block.name,
                        arguments=block.input,
                    ))

            # Cost calculation
            input_cost = (response.usage.input_tokens / 1_000_000) * PRICING.get(self._model, {"input": 3.0})["input"]
            output_cost = (response.usage.output_tokens / 1_000_000) * PRICING.get(self._model, {"output": 15.0})["output"]
            total_cost = input_cost + output_cost

            tracer.end_span(span,
                output_data={
                    "response_text_preview": text_content[:500],
                    "tool_calls": [{"name": tc.name, "args_preview": str(tc.arguments)[:200]} for tc in tool_calls],
                    "duration_ms": round(elapsed_ms, 1),
                },
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                cost_usd=round(total_cost, 8),
            )

            return ModelResponse(
                content=text_content,
                tool_calls=tool_calls,
                provider="anthropic",
                model=self._model,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                cost=total_cost,
                raw_response=response,
            )

        except Exception as e:
            tracer.end_span(span, status=SpanStatus.ERROR, error=str(e))
            raise ModelProviderError("anthropic", str(e)) from e
    
    def calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        pricing = PRICING.get(self._model, {"input": 3.00, "output": 15.00})
        return (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000
