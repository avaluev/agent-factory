"""Ollama adapter for local models with tracing — zero cost."""
import os
import time
import json
import logging
import ollama
from core.models.base import ModelAdapter, ChatMessage, ModelResponse, ToolCall, MessageRole
from core.errors import ModelProviderError

logger = logging.getLogger(__name__)


class OllamaAdapter(ModelAdapter):
    """Ollama adapter for local models — zero cost."""
    
    def __init__(self, model: str = "qwen2.5-coder:14b", **kwargs):
        base_url = kwargs.get("base_url") or os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        super().__init__(base_url=base_url)
        self._model = model
        self._client = ollama.Client(host=base_url)
    
    @property
    def provider_name(self) -> str:
        return "ollama"
    
    @property
    def model_name(self) -> str:
        return self._model
    
    def _format_messages(self, messages: list) -> list[dict]:
        """Convert to Ollama format."""
        converted = []
        for msg in messages:
            role = msg.role if isinstance(msg.role, str) else msg.role.value
            converted.append({
                "role": role if role != "tool" else "user",
                "content": msg.content,
            })
        return converted
    
    async def chat(self, messages: list, tools: list | None = None, temperature: float = 0.7, max_tokens: int = 4096) -> ModelResponse:
        """Call local Ollama model. Traced as llm_call with cost=0."""
        from tracing.tracer import Tracer
        from tracing.models import SpanType, SpanStatus

        tracer = Tracer.instance()
        span = tracer.start_span(
            SpanType.LLM_CALL,
            name=f"ollama:{self._model}",
            input_data={
                "model": self._model,
                "message_count": len(messages),
                "has_tools": bool(tools),
                "last_user_message": next(
                    (m.content[:500] if hasattr(m, 'content') else str(m)[:500]
                     for m in reversed(messages)
                     if (m.role if isinstance(m.role, str) else m.role.value) == "user"),
                    None
                ),
            },
            model=self._model,
            provider="ollama",
        )

        try:
            t0 = time.monotonic()

            ollama_messages = self._format_messages(messages)
            
            kwargs = {
                "model": self._model,
                "messages": ollama_messages,
                "options": {"temperature": temperature, "num_predict": max_tokens},
            }
            if tools:
                kwargs["tools"] = tools
            
            response = self._client.chat(**kwargs)
            elapsed_ms = (time.monotonic() - t0) * 1000

            text_content = response.get("message", {}).get("content", "")
            
            # Parse tool calls if present
            tool_calls = []
            if response.get("message", {}).get("tool_calls"):
                for tc in response["message"]["tool_calls"]:
                    args = tc["function"]["arguments"]
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            args = {}
                    tool_calls.append(ToolCall(
                        id=tc.get("id", f"ollama_{tc['function']['name']}"),
                        name=tc["function"]["name"],
                        arguments=args,
                    ))

            # Estimate tokens (Ollama doesn't always return usage)
            input_tokens = response.get("prompt_eval_count", 0)
            output_tokens = response.get("eval_count", 0)

            tracer.end_span(span,
                output_data={
                    "response_text_preview": text_content[:500],
                    "tool_calls": [{"name": tc.name} for tc in tool_calls],
                    "duration_ms": round(elapsed_ms, 1),
                },
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=0.0,  # Local = free
            )

            return ModelResponse(
                content=text_content,
                tool_calls=tool_calls,
                provider="ollama",
                model=self._model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost=0.0,
                raw_response=response,
            )

        except Exception as e:
            tracer.end_span(span, status=SpanStatus.ERROR, error=str(e))
            raise ModelProviderError("ollama", str(e)) from e
    
    def calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        return 0.0  # Local models are free
