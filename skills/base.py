"""Base skill classes and interfaces."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from enum import Enum


class SkillStatus(Enum):
    """Skill execution status."""
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"
    CANCELLED = "cancelled"


@dataclass
class SkillMetadata:
    """Skill metadata following SKILL.md standard."""
    name: str
    version: str
    description: str
    author: str = "unknown"
    tags: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)
    examples: list[dict[str, Any]] = field(default_factory=list)
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SkillMetadata":
        """Create from dictionary."""
        return cls(
            name=data.get("name", "unknown"),
            version=data.get("version", "0.1.0"),
            description=data.get("description", ""),
            author=data.get("author", "unknown"),
            tags=data.get("tags", []),
            dependencies=data.get("dependencies", []),
            inputs=data.get("inputs", {}),
            outputs=data.get("outputs", {}),
            examples=data.get("examples", [])
        )


@dataclass
class SkillResult:
    """Result of skill execution."""
    status: SkillStatus
    output: Any
    error: str | None = None
    execution_time: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class Skill(ABC):
    """Base class for all skills."""
    
    def __init__(self, metadata: SkillMetadata | None = None):
        self._metadata = metadata or self._default_metadata()
    
    @property
    def metadata(self) -> SkillMetadata:
        """Get skill metadata."""
        return self._metadata
    
    @property
    def name(self) -> str:
        """Get skill name."""
        return self._metadata.name
    
    @abstractmethod
    def _default_metadata(self) -> SkillMetadata:
        """Return default metadata for this skill."""
        ...
    
    @abstractmethod
    async def execute(self, inputs: dict[str, Any]) -> SkillResult:
        """Execute the skill with given inputs."""
        ...
    
    def validate_inputs(self, inputs: dict[str, Any]) -> list[str]:
        """Validate inputs against schema. Returns list of errors."""
        errors = []
        required = self._metadata.inputs.get("required", [])
        properties = self._metadata.inputs.get("properties", {})
        
        for req in required:
            if req not in inputs:
                errors.append(f"Missing required input: {req}")
        
        for key, value in inputs.items():
            if key in properties:
                prop_type = properties[key].get("type")
                if prop_type and not self._check_type(value, prop_type):
                    errors.append(f"Invalid type for {key}: expected {prop_type}")
        
        return errors
    
    def _check_type(self, value: Any, expected: str) -> bool:
        """Check if value matches expected type."""
        type_map = {
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
            "array": list,
            "object": dict
        }
        expected_type = type_map.get(expected)
        if expected_type:
            return isinstance(value, expected_type)
        return True


class CompositeSkill(Skill):
    """Skill composed of multiple sub-skills."""
    
    def __init__(
        self,
        name: str,
        description: str,
        sub_skills: list[Skill]
    ):
        self._sub_skills = sub_skills
        super().__init__(SkillMetadata(
            name=name,
            version="1.0.0",
            description=description,
            dependencies=[s.name for s in sub_skills]
        ))
    
    def _default_metadata(self) -> SkillMetadata:
        return SkillMetadata(
            name="composite",
            version="1.0.0",
            description="Composite skill"
        )
    
    async def execute(self, inputs: dict[str, Any]) -> SkillResult:
        """Execute all sub-skills in sequence."""
        from tracing.tracer import Tracer
        from tracing.models import SpanType, SpanStatus
        
        tracer = Tracer.instance()
        span = tracer.start_span(
            SpanType.SKILL,
            name=f"composite_skill:{self.name}",
            input_data={"sub_skill_count": len(self._sub_skills)}
        )
        
        results = []
        start = datetime.utcnow()
        
        try:
            current_inputs = inputs.copy()
            
            for skill in self._sub_skills:
                result = await skill.execute(current_inputs)
                results.append(result)
                
                if result.status == SkillStatus.FAILURE:
                    tracer.end_span(span, status=SpanStatus.ERROR, error=result.error)
                    return SkillResult(
                        status=SkillStatus.FAILURE,
                        output=results,
                        error=f"Sub-skill {skill.name} failed: {result.error}",
                        execution_time=(datetime.utcnow() - start).total_seconds()
                    )
                
                # Pass output to next skill
                if isinstance(result.output, dict):
                    current_inputs.update(result.output)
            
            tracer.end_span(span, status=SpanStatus.SUCCESS, output_data={"results": len(results)})
            return SkillResult(
                status=SkillStatus.SUCCESS,
                output=results,
                execution_time=(datetime.utcnow() - start).total_seconds()
            )
            
        except Exception as e:
            tracer.end_span(span, status=SpanStatus.ERROR, error=str(e))
            return SkillResult(
                status=SkillStatus.FAILURE,
                output=None,
                error=str(e),
                execution_time=(datetime.utcnow() - start).total_seconds()
            )
