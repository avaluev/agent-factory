"""Base classes for all model adapters."""
from dataclasses import dataclass, field
from typing import Any
from enum import Enum


class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class ChatMessage:
    role: MessageRole | str
    content: str
    tool_call_id: str | None = None
    tool_name: str | None = None
    tool_calls: list["ToolCall"] | None = None  # For assistant messages with tool calls
    metadata: dict | None = None


@dataclass  
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class ModelResponse:
    content: str
    tool_calls: list[ToolCall]
    provider: str = ""
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
    raw_response: Any = None


class ModelAdapter:
    """Abstract base — all provider adapters must implement this."""
    
    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = api_key
        self.base_url = base_url
    
    async def chat(
        self,
        messages: list[ChatMessage],
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> ModelResponse:
        raise NotImplementedError
    
    def calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        raise NotImplementedError
    
    @property
    def provider_name(self) -> str:
        raise NotImplementedError
    
    @property
    def model_name(self) -> str:
        raise NotImplementedError
