"""Workflow tools for agent use."""

from core.tool_registry import ToolRegistry, ToolSchema


def register_workflow_tools() -> None:
    """Register workflow tools with the tool registry."""
    registry = ToolRegistry.instance()
    
    # Execute workflow tool
    registry.register(
        schema=ToolSchema(
            name="workflow_execute",
            description="Execute a registered workflow with given inputs.",
            parameters={
                "type": "object",
                "properties": {
                    "workflow_id": {
                        "type": "string",
                        "description": "ID of the workflow to execute"
                    },
                    "inputs": {
                        "type": "object",
                        "description": "Input parameters for the workflow"
                    }
                },
                "required": ["workflow_id"]
            }
        ),
        handler=_handle_workflow_execute
    )
    
    # List workflows tool
    registry.register(
        schema=ToolSchema(
            name="workflow_list",
            description="List all registered workflows.",
            parameters={
                "type": "object",
                "properties": {}
            }
        ),
        handler=_handle_workflow_list
    )


async def _handle_workflow_execute(params: dict) -> dict:
    """Handle workflow execution tool call."""
    from workflows.engine import WorkflowEngine
    
    workflow_id = params.get("workflow_id", "")
    inputs = params.get("inputs", {})
    
    if not workflow_id:
        return {"error": "workflow_id is required"}
    
    engine = WorkflowEngine.instance()
    workflow = engine.get(workflow_id)
    
    if not workflow:
        return {"error": f"Workflow not found: {workflow_id}"}
    
    run = await engine.execute(workflow_id, inputs)
    
    return {
        "run_id": run.id,
        "workflow_id": workflow_id,
        "status": run.status,
        "context": run.context,
        "error": run.error
    }


async def _handle_workflow_list(params: dict) -> dict:
    """Handle workflow list tool call."""
    from workflows.engine import WorkflowEngine
    
    engine = WorkflowEngine.instance()
    workflow_ids = engine.list_workflows()
    
    workflows = []
    for wid in workflow_ids:
        workflow = engine.get(wid)
        if workflow:
            workflows.append({
                "id": workflow.id,
                "name": workflow.name,
                "description": workflow.description,
                "node_count": len(workflow.nodes)
            })
    
    return {
        "workflows": workflows,
        "total": len(workflows)
    }
