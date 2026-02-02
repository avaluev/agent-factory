"""Cost-optimized LLM router."""

from dataclasses import dataclass, field
from typing import Any
from enum import Enum

from core.models.base import ModelAdapter, ChatMessage, ModelResponse


class ModelTier(Enum):
    """Model capability tiers."""
    LOCAL = "local"       # Free, local models (Ollama)
    CHEAP = "cheap"       # Low-cost API models
    STANDARD = "standard" # Standard API models
    PREMIUM = "premium"   # High-capability models


@dataclass
class ModelConfig:
    """Configuration for a model in the router."""
    name: str
    adapter: ModelAdapter
    tier: ModelTier
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0
    max_tokens: int = 4096
    supports_tools: bool = True
    supports_vision: bool = False
    quality_score: float = 0.5  # 0-1 quality rating
    latency_ms: float = 1000    # Average latency
    
    @property
    def cost_score(self) -> float:
        """Lower is cheaper."""
        return self.cost_per_1k_input + self.cost_per_1k_output


@dataclass
class RoutingDecision:
    """Result of routing decision."""
    model: ModelConfig
    reason: str
    alternatives: list[str] = field(default_factory=list)


class CostRouter:
    """Routes requests to optimal LLM based on cost/quality."""
    
    _instance: "CostRouter | None" = None
    
    def __init__(self):
        self._models: dict[str, ModelConfig] = {}
        self._usage_stats: dict[str, dict[str, Any]] = {}
        self._total_cost: float = 0.0
        self._strategy: "RoutingStrategy | None" = None
    
    @classmethod
    def instance(cls) -> "CostRouter":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def reset(cls) -> None:
        """Reset singleton for testing."""
        cls._instance = None
    
    def register(self, config: ModelConfig) -> None:
        """Register a model configuration."""
        self._models[config.name] = config
        self._usage_stats[config.name] = {
            "calls": 0,
            "tokens_in": 0,
            "tokens_out": 0,
            "cost": 0.0,
            "errors": 0
        }
    
    def set_strategy(self, strategy: "RoutingStrategy") -> None:
        """Set routing strategy."""
        self._strategy = strategy
    
    def route(
        self,
        task_complexity: str = "medium",
        requires_tools: bool = False,
        requires_vision: bool = False,
        max_cost: float | None = None,
        preferred_model: str | None = None
    ) -> RoutingDecision:
        """Route request to optimal model."""
        from tracing.tracer import Tracer
        from tracing.models import SpanType, SpanStatus
        
        tracer = Tracer.instance()
        span = tracer.start_span(
            SpanType.ROUTING,
            name="model_routing",
            input_data={
                "complexity": task_complexity,
                "requires_tools": requires_tools,
                "requires_vision": requires_vision
            }
        )
        
        try:
            # Use strategy if set
            if self._strategy:
                decision = self._strategy.select(
                    models=list(self._models.values()),
                    task_complexity=task_complexity,
                    requires_tools=requires_tools,
                    requires_vision=requires_vision,
                    max_cost=max_cost,
                    preferred_model=preferred_model
                )
            else:
                decision = self._default_routing(
                    task_complexity,
                    requires_tools,
                    requires_vision,
                    max_cost,
                    preferred_model
                )
            
            tracer.end_span(span, status=SpanStatus.SUCCESS, output_data={
                "selected": decision.model.name,
                "reason": decision.reason
            })
            return decision
            
        except Exception as e:
            tracer.end_span(span, status=SpanStatus.ERROR, error=str(e))
            raise
    
    def _default_routing(
        self,
        task_complexity: str,
        requires_tools: bool,
        requires_vision: bool,
        max_cost: float | None,
        preferred_model: str | None
    ) -> RoutingDecision:
        """Default routing logic."""
        # Filter eligible models
        eligible = []
        for model in self._models.values():
            if requires_tools and not model.supports_tools:
                continue
            if requires_vision and not model.supports_vision:
                continue
            if max_cost and model.cost_score > max_cost:
                continue
            eligible.append(model)
        
        if not eligible:
            raise ValueError("No eligible models found for requirements")
        
        # Prefer specified model
        if preferred_model and preferred_model in self._models:
            model = self._models[preferred_model]
            if model in eligible:
                return RoutingDecision(
                    model=model,
                    reason="Preferred model selected",
                    alternatives=[m.name for m in eligible if m != model][:3]
                )
        
        # Route by complexity
        complexity_tiers = {
            "simple": [ModelTier.LOCAL, ModelTier.CHEAP],
            "medium": [ModelTier.CHEAP, ModelTier.STANDARD],
            "complex": [ModelTier.STANDARD, ModelTier.PREMIUM],
            "critical": [ModelTier.PREMIUM]
        }
        
        preferred_tiers = complexity_tiers.get(task_complexity, [ModelTier.STANDARD])
        
        # Sort by tier preference, then cost
        def sort_key(m: ModelConfig) -> tuple:
            tier_priority = (
                0 if m.tier in preferred_tiers 
                else 1
            )
            return (tier_priority, m.cost_score, -m.quality_score)
        
        eligible.sort(key=sort_key)
        selected = eligible[0]
        
        return RoutingDecision(
            model=selected,
            reason=f"Selected {selected.tier.value} tier for {task_complexity} task",
            alternatives=[m.name for m in eligible[1:4]]
        )
    
    async def chat(
        self,
        messages: list[ChatMessage],
        task_complexity: str = "medium",
        **kwargs
    ) -> ModelResponse:
        """Route and execute chat request."""
        from tracing.tracer import Tracer
        from tracing.models import SpanType, SpanStatus
        
        tracer = Tracer.instance()
        span = tracer.start_span(
            SpanType.LLM_CALL,
            name="routed_chat",
            input_data={"message_count": len(messages), "complexity": task_complexity}
        )
        
        try:
            # Determine requirements
            requires_tools = kwargs.get("tools") is not None
            requires_vision = any(
                hasattr(m, "images") and m.images 
                for m in messages
            )
            
            # Route to model
            decision = self.route(
                task_complexity=task_complexity,
                requires_tools=requires_tools,
                requires_vision=requires_vision,
                max_cost=kwargs.pop("max_cost", None),
                preferred_model=kwargs.pop("preferred_model", None)
            )
            
            model = decision.model
            
            # Execute chat
            response = await model.adapter.chat(messages, **kwargs)
            
            # Track usage
            self._track_usage(model.name, response)
            
            tracer.end_span(span, status=SpanStatus.SUCCESS, output_data={
                "model": model.name,
                "tokens": response.usage.get("total_tokens", 0) if response.usage else 0
            })
            return response
            
        except Exception as e:
            tracer.end_span(span, status=SpanStatus.ERROR, error=str(e))
            raise
    
    def _track_usage(self, model_name: str, response: ModelResponse) -> None:
        """Track model usage statistics."""
        stats = self._usage_stats.get(model_name, {})
        model = self._models.get(model_name)
        
        if response.usage:
            tokens_in = response.usage.get("prompt_tokens", 0)
            tokens_out = response.usage.get("completion_tokens", 0)
            
            stats["calls"] = stats.get("calls", 0) + 1
            stats["tokens_in"] = stats.get("tokens_in", 0) + tokens_in
            stats["tokens_out"] = stats.get("tokens_out", 0) + tokens_out
            
            if model:
                cost = (
                    (tokens_in / 1000) * model.cost_per_1k_input +
                    (tokens_out / 1000) * model.cost_per_1k_output
                )
                stats["cost"] = stats.get("cost", 0) + cost
                self._total_cost += cost
        
        self._usage_stats[model_name] = stats
    
    def get_usage_stats(self) -> dict[str, Any]:
        """Get usage statistics."""
        return {
            "by_model": self._usage_stats.copy(),
            "total_cost": self._total_cost,
            "total_calls": sum(s.get("calls", 0) for s in self._usage_stats.values())
        }
    
    def get_model(self, name: str) -> ModelConfig | None:
        """Get model config by name."""
        return self._models.get(name)
    
    def list_models(self) -> list[str]:
        """List registered model names."""
        return list(self._models.keys())


# Import strategies at module level to avoid circular imports
from router.strategies import RoutingStrategy
