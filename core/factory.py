"""Agent System Factory - Orchestrates autonomous system building from ideas."""

import asyncio
import json
from datetime import datetime
from typing import Any
from dataclasses import dataclass, field

from core.agent import Agent
from memory.manager import MemoryManager
from skills.executor import SkillExecutor
from workflows.engine import WorkflowEngine
from workflows.models import WorkflowDefinition, WorkflowNode


@dataclass
class FactoryProject:
    """Represents a factory project."""
    id: str
    idea: str
    plan: dict[str, Any]
    status: str  # "planning" | "executing" | "completed" | "failed"
    tasks: list[dict[str, Any]] = field(default_factory=list)
    completed_tasks: list[str] = field(default_factory=list)
    current_task: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    error: str | None = None


class SystemBuilderFactory:
    """High-level orchestrator for autonomous system building."""
    
    _instance: "SystemBuilderFactory | None" = None
    
    def __init__(
        self,
        agent: Agent | None = None,
        memory: MemoryManager | None = None,
        skill_executor: SkillExecutor | None = None
    ):
        self.agent = agent or Agent()
        self.memory = memory or MemoryManager.instance()
        self.skill_executor = skill_executor or SkillExecutor.instance()
        self._projects: dict[str, FactoryProject] = {}
    
    @classmethod
    def instance(cls) -> "SystemBuilderFactory":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def reset(cls) -> None:
        """Reset singleton for testing."""
        cls._instance = None
    
    async def create_from_idea(
        self,
        idea: str,
        detail_level: str = "medium"
    ) -> FactoryProject:
        """Create a new project from an idea.
        
        Steps:
        1. Generate implementation plan using ProjectPlanner
        2. Store plan in memory
        3. Create project tracking structure
        4. Return project for execution
        """
        from tracing.tracer import Tracer
        from tracing.models import SpanType, SpanStatus
        import hashlib
        
        tracer = Tracer.instance()
        span = tracer.start_span(
            SpanType.AGENT_RUN,
            name="factory_create_project",
            input_data={"idea": idea[:200]}
        )
        
        try:
            # Generate project ID
            project_id = hashlib.sha256(
                f"{idea}{datetime.utcnow().isoformat()}".encode()
            ).hexdigest()[:12]
            
            print(f"🏭 Agent Factory: Creating project {project_id}")
            print(f"💡 Idea: {idea}")
            print(f"📋 Generating implementation plan...")
            
            # Step 1: Generate plan using ProjectPlanner skill
            from skills.base import SkillStatus

            plan_result = await self.skill_executor.execute(
                "project_planner",
                {"idea": idea, "detail_level": detail_level}
            )

            if plan_result.status != SkillStatus.SUCCESS:
                raise ValueError(f"Planning failed: {plan_result.error}")
            
            plan_data = plan_result.output["plan"]
            tasks = plan_result.output["tasks"]
            
            print(f"✅ Plan created: {len(tasks)} tasks")
            
            # Step 2: Store in long-term memory
            await self.memory.store_fact(
                content=f"Project Plan: {idea}\n\nTasks: {len(tasks)}\nOverview: {plan_data.get('overview', '')}",
                category="project_plan",
                importance=0.9
            )
            
            # Step 3: Create project structure
            project = FactoryProject(
                id=project_id,
                idea=idea,
                plan=plan_data,
                status="planning",
                tasks=tasks
            )
            
            self._projects[project_id] = project
            
            tracer.end_span(span, status=SpanStatus.SUCCESS, output_data={
                "project_id": project_id,
                "task_count": len(tasks)
            })
            
            return project
            
        except Exception as e:
            tracer.end_span(span, status=SpanStatus.ERROR, error=str(e))
            raise
    
    async def execute_project(self, project_id: str) -> dict[str, Any]:
        """Execute a project's implementation plan.
        
        Steps:
        1. Load project
        2. For each task in dependency order:
           - Mark as current
           - Execute using agent
           - Store result in memory
           - Update progress
        3. Mark project complete
        """
        from tracing.tracer import Tracer
        from tracing.models import SpanType, SpanStatus
        
        tracer = Tracer.instance()
        span = tracer.start_span(
            SpanType.AGENT_RUN,
            name="factory_execute_project",
            input_data={"project_id": project_id}
        )
        
        try:
            project = self._projects.get(project_id)
            if not project:
                raise ValueError(f"Project not found: {project_id}")
            
            print(f"\n🚀 Starting execution: {project.idea}")
            print(f"📊 Total tasks: {len(project.tasks)}\n")
            
            project.status = "executing"
            project.updated_at = datetime.utcnow()
            
            # Execute tasks in order (simple sequential for now)
            for i, task in enumerate(project.tasks, 1):
                task_id = task["id"]
                
                # Check dependencies
                deps = task.get("dependencies", [])
                if not all(dep in project.completed_tasks for dep in deps):
                    print(f"⏭️  Skipping {task_id}: dependencies not met")
                    continue
                
                project.current_task = task_id
                project.updated_at = datetime.utcnow()
                
                print(f"📌 Task {i}/{len(project.tasks)}: {task['title']}")
                print(f"   Category: {task.get('category', 'general')}")
                print(f"   Complexity: {task.get('complexity', 'medium')}")
                
                # Execute task using agent
                task_prompt = f"""Execute this implementation task:

**Task**: {task['title']}
**Description**: {task['description']}
**Category**: {task.get('category', 'general')}

**Context**: Part of project: {project.idea}

Use available tools to complete this task. Report what you did and mark it complete."""
                
                try:
                    result = await self.agent.run(task_prompt)
                    
                    # Store in episodic memory
                    await self.memory.episodic.record(
                        task=task['title'],
                        outcome="success",
                        steps=[{"action": "agent_execution", "result": result[:500]}],
                        result=result,
                        started_at=datetime.utcnow()
                    )
                    
                    project.completed_tasks.append(task_id)
                    print(f"   ✅ Completed\n")
                    
                except Exception as e:
                    print(f"   ❌ Failed: {e}\n")
                    # Store failure in memory
                    await self.memory.episodic.record(
                        task=task['title'],
                        outcome="failure",
                        steps=[{"action": "agent_execution", "error": str(e)}],
                        result=str(e),
                        started_at=datetime.utcnow()
                    )
            
            # Mark complete
            project.status = "completed"
            project.current_task = None
            project.updated_at = datetime.utcnow()
            
            completion_rate = len(project.completed_tasks) / len(project.tasks)
            
            print(f"\n🎉 Project Execution Complete!")
            print(f"✅ Completed: {len(project.completed_tasks)}/{len(project.tasks)} tasks ({completion_rate*100:.1f}%)")
            
            tracer.end_span(span, status=SpanStatus.SUCCESS, output_data={
                "completed_tasks": len(project.completed_tasks),
                "total_tasks": len(project.tasks),
                "completion_rate": completion_rate
            })
            
            return {
                "project_id": project_id,
                "status": project.status,
                "completed_tasks": len(project.completed_tasks),
                "total_tasks": len(project.tasks),
                "completion_rate": completion_rate
            }
            
        except Exception as e:
            if project_id in self._projects:
                self._projects[project_id].status = "failed"
                self._projects[project_id].error = str(e)
            
            tracer.end_span(span, status=SpanStatus.ERROR, error=str(e))
            raise
    
    def get_project(self, project_id: str) -> FactoryProject | None:
        """Get project by ID."""
        return self._projects.get(project_id)
    
    def list_projects(self) -> list[FactoryProject]:
        """List all projects."""
        return list(self._projects.values())
    
    def get_project_status(self, project_id: str) -> dict[str, Any]:
        """Get detailed project status."""
        project = self._projects.get(project_id)
        if not project:
            return {"error": "Project not found"}
        
        return {
            "id": project.id,
            "idea": project.idea,
            "status": project.status,
            "total_tasks": len(project.tasks),
            "completed_tasks": len(project.completed_tasks),
            "current_task": project.current_task,
            "progress_percent": (len(project.completed_tasks) / len(project.tasks) * 100) if project.tasks else 0,
            "created_at": project.created_at.isoformat(),
            "updated_at": project.updated_at.isoformat(),
            "error": project.error
        }
