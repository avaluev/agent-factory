"""Skill tools for agent use."""

from core.tool_registry import ToolRegistry, ToolSchema


def register_skill_tools() -> None:
    """Register skill tools with the tool registry."""
    registry = ToolRegistry.instance()
    
    # Execute skill tool
    registry.register(
        schema=ToolSchema(
            name="execute_skill",
            description="Execute a registered skill with given inputs.",
            parameters={
                "type": "object",
                "properties": {
                    "skill_name": {
                        "type": "string",
                        "description": "Name of the skill to execute"
                    },
                    "inputs": {
                        "type": "object",
                        "description": "Input parameters for the skill"
                    }
                },
                "required": ["skill_name", "inputs"]
            }
        ),
        handler=_handle_execute_skill
    )
    
    # List skills tool
    registry.register(
        schema=ToolSchema(
            name="list_skills",
            description="List all available skills and their descriptions.",
            parameters={
                "type": "object",
                "properties": {}
            }
        ),
        handler=_handle_list_skills
    )


async def _handle_execute_skill(params: dict) -> dict:
    """Handle skill execution tool call."""
    from skills.executor import SkillExecutor
    
    skill_name = params.get("skill_name", "")
    inputs = params.get("inputs", {})
    
    if not skill_name:
        return {"error": "skill_name is required"}
    
    executor = SkillExecutor.instance()
    result = await executor.execute(skill_name, inputs)
    
    return {
        "skill": skill_name,
        "status": result.status.value,
        "output": result.output,
        "error": result.error,
        "execution_time": result.execution_time
    }


async def _handle_list_skills(params: dict) -> dict:
    """Handle list skills tool call."""
    from skills.loader import SkillLoader
    
    loader = SkillLoader.instance()
    skills = loader.discover()
    
    return {
        "skills": [
            {
                "name": meta.name,
                "description": meta.description,
                "version": meta.version,
                "tags": meta.tags
            }
            for meta in skills.values()
        ],
        "total": len(skills)
    }
