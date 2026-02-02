"""Routing strategies for model selection."""

from abc import ABC, abstractmethod
from typing import Any


class RoutingStrategy(ABC):
    """Base class for routing strategies."""
    
    @abstractmethod
    def select(
        self,
        models: list["ModelConfig"],
        task_complexity: str,
        requires_tools: bool,
        requires_vision: bool,
        max_cost: float | None,
        preferred_model: str | None
    ) -> "RoutingDecision":
        """Select optimal model based on strategy."""
        ...


class CostOptimizedStrategy(RoutingStrategy):
    """Prioritize lowest cost while meeting requirements."""
    
    def select(
        self,
        models: list["ModelConfig"],
        task_complexity: str,
        requires_tools: bool,
        requires_vision: bool,
        max_cost: float | None,
        preferred_model: str | None
    ) -> "RoutingDecision":
        from router.cost_router import RoutingDecision, ModelTier
        
        # Filter eligible
        eligible = self._filter_eligible(
            models, requires_tools, requires_vision, max_cost
        )
        
        if not eligible:
            raise ValueError("No eligible models")
        
        # Sort by cost (cheapest first)
        eligible.sort(key=lambda m: (m.cost_score, -m.quality_score))
        
        # For simple tasks, prefer local/free models
        if task_complexity == "simple":
            local = [m for m in eligible if m.tier == ModelTier.LOCAL]
            if local:
                return RoutingDecision(
                    model=local[0],
                    reason="Cost-optimized: using free local model for simple task",
                    alternatives=[m.name for m in eligible[1:4]]
                )
        
        return RoutingDecision(
            model=eligible[0],
            reason=f"Cost-optimized: cheapest eligible model (${eligible[0].cost_score:.4f}/1k)",
            alternatives=[m.name for m in eligible[1:4]]
        )
    
    def _filter_eligible(
        self,
        models: list["ModelConfig"],
        requires_tools: bool,
        requires_vision: bool,
        max_cost: float | None
    ) -> list["ModelConfig"]:
        eligible = []
        for model in models:
            if requires_tools and not model.supports_tools:
                continue
            if requires_vision and not model.supports_vision:
                continue
            if max_cost and model.cost_score > max_cost:
                continue
            eligible.append(model)
        return eligible


class QualityFirstStrategy(RoutingStrategy):
    """Prioritize quality while respecting cost limits."""
    
    def __init__(self, quality_threshold: float = 0.7):
        self.quality_threshold = quality_threshold
    
    def select(
        self,
        models: list["ModelConfig"],
        task_complexity: str,
        requires_tools: bool,
        requires_vision: bool,
        max_cost: float | None,
        preferred_model: str | None
    ) -> "RoutingDecision":
        from router.cost_router import RoutingDecision, ModelTier
        
        # Filter eligible
        eligible = []
        for model in models:
            if requires_tools and not model.supports_tools:
                continue
            if requires_vision and not model.supports_vision:
                continue
            if max_cost and model.cost_score > max_cost:
                continue
            eligible.append(model)
        
        if not eligible:
            raise ValueError("No eligible models")
        
        # Sort by quality (highest first), then cost
        eligible.sort(key=lambda m: (-m.quality_score, m.cost_score))
        
        # For complex/critical tasks, require high quality
        if task_complexity in ["complex", "critical"]:
            high_quality = [m for m in eligible if m.quality_score >= self.quality_threshold]
            if high_quality:
                return RoutingDecision(
                    model=high_quality[0],
                    reason=f"Quality-first: highest quality model for {task_complexity} task",
                    alternatives=[m.name for m in high_quality[1:4]]
                )
        
        return RoutingDecision(
            model=eligible[0],
            reason=f"Quality-first: best quality/cost balance (quality={eligible[0].quality_score})",
            alternatives=[m.name for m in eligible[1:4]]
        )


class LatencyOptimizedStrategy(RoutingStrategy):
    """Prioritize low latency for time-sensitive tasks."""
    
    def __init__(self, max_latency_ms: float = 2000):
        self.max_latency_ms = max_latency_ms
    
    def select(
        self,
        models: list["ModelConfig"],
        task_complexity: str,
        requires_tools: bool,
        requires_vision: bool,
        max_cost: float | None,
        preferred_model: str | None
    ) -> "RoutingDecision":
        from router.cost_router import RoutingDecision, ModelTier
        
        # Filter eligible
        eligible = []
        for model in models:
            if requires_tools and not model.supports_tools:
                continue
            if requires_vision and not model.supports_vision:
                continue
            if max_cost and model.cost_score > max_cost:
                continue
            eligible.append(model)
        
        if not eligible:
            raise ValueError("No eligible models")
        
        # Prefer low-latency models
        fast = [m for m in eligible if m.latency_ms <= self.max_latency_ms]
        if fast:
            # Sort fast models by quality
            fast.sort(key=lambda m: (-m.quality_score, m.latency_ms))
            return RoutingDecision(
                model=fast[0],
                reason=f"Latency-optimized: {fast[0].latency_ms}ms response time",
                alternatives=[m.name for m in fast[1:4]]
            )
        
        # Fallback to fastest available
        eligible.sort(key=lambda m: m.latency_ms)
        return RoutingDecision(
            model=eligible[0],
            reason=f"Latency-optimized: fastest available ({eligible[0].latency_ms}ms)",
            alternatives=[m.name for m in eligible[1:4]]
        )


# Type hints need forward references
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from router.cost_router import ModelConfig, RoutingDecision
