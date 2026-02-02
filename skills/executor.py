"""Skill executor with tracing and error handling."""

from datetime import datetime
from typing import Any

from skills.base import Skill, SkillResult, SkillStatus
from skills.loader import SkillLoader


class SkillExecutor:
    """Executes skills with full tracing and error handling."""
    
    _instance: "SkillExecutor | None" = None
    
    def __init__(self, loader: SkillLoader | None = None):
        self.loader = loader or SkillLoader.instance()
        self._execution_history: list[dict[str, Any]] = []
    
    @classmethod
    def instance(cls) -> "SkillExecutor":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def reset(cls) -> None:
        """Reset singleton for testing."""
        cls._instance = None
    
    async def execute(
        self,
        skill_name: str,
        inputs: dict[str, Any]
    ) -> SkillResult:
        """Execute a skill by name."""
        from tracing.tracer import Tracer
        from tracing.models import SpanType, SpanStatus
        
        tracer = Tracer.instance()
        span = tracer.start_span(
            SpanType.SKILL,
            name=f"skill_execute:{skill_name}",
            input_data={"skill": skill_name, "inputs": inputs}
        )
        
        start = datetime.utcnow()
        
        try:
            # Load skill
            skill = self.loader.load(skill_name)
            
            # Validate inputs
            validation_errors = skill.validate_inputs(inputs)
            if validation_errors:
                result = SkillResult(
                    status=SkillStatus.FAILURE,
                    output=None,
                    error=f"Validation failed: {', '.join(validation_errors)}",
                    execution_time=(datetime.utcnow() - start).total_seconds()
                )
                tracer.end_span(span, status=SpanStatus.ERROR, error=result.error)
                self._record_execution(skill_name, inputs, result)
                return result
            
            # Execute skill
            result = await skill.execute(inputs)
            result.execution_time = (datetime.utcnow() - start).total_seconds()
            
            # Record and trace
            self._record_execution(skill_name, inputs, result)
            
            if result.status == SkillStatus.SUCCESS:
                tracer.end_span(span, status=SpanStatus.SUCCESS, output_data={
                    "status": result.status.value,
                    "execution_time": result.execution_time
                })
            else:
                tracer.end_span(span, status=SpanStatus.ERROR, error=result.error)
            
            return result
            
        except Exception as e:
            result = SkillResult(
                status=SkillStatus.FAILURE,
                output=None,
                error=str(e),
                execution_time=(datetime.utcnow() - start).total_seconds()
            )
            self._record_execution(skill_name, inputs, result)
            tracer.end_span(span, status=SpanStatus.ERROR, error=str(e))
            return result
    
    async def execute_skill(self, skill: Skill, inputs: dict[str, Any]) -> SkillResult:
        """Execute a skill instance directly."""
        from tracing.tracer import Tracer
        from tracing.models import SpanType, SpanStatus
        
        tracer = Tracer.instance()
        span = tracer.start_span(
            SpanType.SKILL,
            name=f"skill_execute:{skill.name}",
            input_data={"skill": skill.name, "inputs": inputs}
        )
        
        start = datetime.utcnow()
        
        try:
            result = await skill.execute(inputs)
            result.execution_time = (datetime.utcnow() - start).total_seconds()
            
            if result.status == SkillStatus.SUCCESS:
                tracer.end_span(span, status=SpanStatus.SUCCESS, output_data={
                    "status": result.status.value
                })
            else:
                tracer.end_span(span, status=SpanStatus.ERROR, error=result.error)
            
            return result
            
        except Exception as e:
            tracer.end_span(span, status=SpanStatus.ERROR, error=str(e))
            return SkillResult(
                status=SkillStatus.FAILURE,
                output=None,
                error=str(e),
                execution_time=(datetime.utcnow() - start).total_seconds()
            )
    
    def _record_execution(
        self,
        skill_name: str,
        inputs: dict[str, Any],
        result: SkillResult
    ) -> None:
        """Record skill execution in history."""
        self._execution_history.append({
            "skill": skill_name,
            "inputs": inputs,
            "status": result.status.value,
            "error": result.error,
            "execution_time": result.execution_time,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Keep only last 100 executions
        if len(self._execution_history) > 100:
            self._execution_history = self._execution_history[-100:]
    
    def get_history(self, skill_name: str | None = None) -> list[dict[str, Any]]:
        """Get execution history, optionally filtered by skill."""
        if skill_name:
            return [
                h for h in self._execution_history
                if h["skill"] == skill_name
            ]
        return self._execution_history.copy()
    
    def get_stats(self) -> dict[str, Any]:
        """Get execution statistics."""
        if not self._execution_history:
            return {"total": 0, "success_rate": 0}
        
        total = len(self._execution_history)
        success = sum(1 for h in self._execution_history if h["status"] == "success")
        avg_time = sum(h["execution_time"] for h in self._execution_history) / total
        
        return {
            "total": total,
            "success": success,
            "failure": total - success,
            "success_rate": success / total,
            "avg_execution_time": avg_time
        }
