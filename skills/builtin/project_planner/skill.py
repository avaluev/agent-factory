"""Project Planner Skill - Transforms ideas into implementation plans."""

import json
from datetime import datetime
from typing import Any
from skills.base import Skill, SkillMetadata, SkillResult, SkillStatus


class ProjectPlannerSkill(Skill):
    """Analyzes ideas and creates comprehensive implementation plans."""
    
    def _default_metadata(self) -> SkillMetadata:
        return SkillMetadata(
            name="project_planner",
            version="1.0.0",
            description="Analyzes user ideas and creates comprehensive implementation plans",
            tags=["planning", "architecture", "project-management"],
            inputs={
                "type": "object",
                "properties": {
                    "idea": {
                        "type": "string",
                        "description": "User's project idea or system concept"
                    },
                    "detail_level": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                        "default": "medium"
                    }
                },
                "required": ["idea"]
            },
            outputs={
                "type": "object",
                "properties": {
                    "plan": {"type": "object"},
                    "tasks": {"type": "array"},
                    "dependencies": {"type": "object"}
                }
            }
        )
    
    async def execute(self, inputs: dict[str, Any]) -> SkillResult:
        """Create a project plan from an idea."""
        from tracing.tracer import Tracer
        from tracing.models import SpanType, SpanStatus
        from core.agent import Agent
        from core.models.anthropic_adapter import AnthropicAdapter
        
        tracer = Tracer.instance()
        span = tracer.start_span(
            SpanType.SKILL,
            name="project_planner_execute",
            input_data={"idea": inputs["idea"][:200]}
        )
        
        start_time = datetime.utcnow()
        
        try:
            idea = inputs["idea"]
            detail_level = inputs.get("detail_level", "medium")
            
            # Use Claude for planning (better at structured reasoning)
            planner_agent = Agent(model_adapter=AnthropicAdapter())
            
            planning_prompt = f"""You are a software architect and project planner. Analyze this idea and create a detailed implementation plan.

IDEA: {idea}

Create a plan with:
1. **Project Overview**: Brief description and goals
2. **Technology Stack**: Recommended technologies
3. **Architecture**: High-level system design
4. **Task Breakdown**: 15-30 specific implementation tasks
5. **Dependencies**: Which tasks depend on others
6. **Success Criteria**: How to know it's complete
7. **Risks**: Potential challenges

For each task provide:
- ID (task_1, task_2, etc.)
- Title (brief, actionable)
- Description (what needs to be done)
- Dependencies (list of task IDs that must complete first)
- Estimated complexity (low/medium/high)
- Category (setup/core/feature/testing/deployment)

Format as JSON with this structure:
{{
  "overview": "...",
  "tech_stack": ["tech1", "tech2"],
  "architecture": "...",
  "tasks": [
    {{
      "id": "task_1",
      "title": "...",
      "description": "...",
      "dependencies": [],
      "complexity": "medium",
      "category": "setup"
    }}
  ],
  "success_criteria": ["..."],
  "risks": ["..."]
}}

Be specific and actionable. Detail level: {detail_level}."""
            
            # Get plan from agent
            plan_response = await planner_agent.run(planning_prompt)
            
            # Parse JSON from response
            plan_data = self._extract_json(plan_response)
            
            if not plan_data:
                raise ValueError("Failed to generate valid plan structure")
            
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            
            result = SkillResult(
                status=SkillStatus.SUCCESS,
                output={
                    "plan": plan_data,
                    "tasks": plan_data.get("tasks", []),
                    "task_count": len(plan_data.get("tasks", [])),
                    "created_at": datetime.utcnow().isoformat()
                },
                execution_time=execution_time
            )
            
            tracer.end_span(span, status=SpanStatus.SUCCESS, output_data={
                "task_count": len(plan_data.get("tasks", [])),
                "execution_time": execution_time
            })
            
            return result
            
        except Exception as e:
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            tracer.end_span(span, status=SpanStatus.ERROR, error=str(e))
            
            return SkillResult(
                status=SkillStatus.FAILURE,
                output=None,
                error=str(e),
                execution_time=execution_time
            )
    
    def _extract_json(self, text: str) -> dict | None:
        """Extract JSON from text response."""
        import re
        
        # Try to find JSON in code blocks
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        
        # Try to find raw JSON
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass
        
        return None
