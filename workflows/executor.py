"""Workflow executor with builder pattern."""

from typing import Any, Callable, Awaitable
import uuid

from workflows.models import (
    WorkflowDefinition, WorkflowNode, WorkflowEdge,
    NodeType
)
from workflows.engine import WorkflowEngine


class WorkflowBuilder:
    """Fluent builder for workflow definitions."""
    
    def __init__(self, name: str, description: str = ""):
        self._workflow = WorkflowDefinition(
            id=str(uuid.uuid4())[:8],
            name=name,
            description=description
        )
        self._node_counter = 0
    
    def _next_id(self, prefix: str = "node") -> str:
        """Generate next node ID."""
        self._node_counter += 1
        return f"{prefix}_{self._node_counter}"
    
    def start(self) -> "WorkflowBuilder":
        """Add start node."""
        node = WorkflowNode(
            id="start",
            name="Start",
            node_type=NodeType.START
        )
        self._workflow.nodes.append(node)
        return self
    
    def end(self) -> "WorkflowBuilder":
        """Add end node."""
        node = WorkflowNode(
            id="end",
            name="End",
            node_type=NodeType.END
        )
        self._workflow.nodes.append(node)
        return self
    
    def task(
        self,
        name: str,
        handler: str | Callable[..., Awaitable[Any]],
        config: dict[str, Any] | None = None,
        node_id: str | None = None
    ) -> "WorkflowBuilder":
        """Add task node."""
        node = WorkflowNode(
            id=node_id or self._next_id("task"),
            name=name,
            node_type=NodeType.TASK,
            handler=handler,
            config=config or {}
        )
        self._workflow.nodes.append(node)
        return self
    
    def decision(
        self,
        name: str,
        node_id: str | None = None
    ) -> "WorkflowBuilder":
        """Add decision node."""
        node = WorkflowNode(
            id=node_id or self._next_id("decision"),
            name=name,
            node_type=NodeType.DECISION
        )
        self._workflow.nodes.append(node)
        return self
    
    def parallel(self, node_id: str | None = None) -> "WorkflowBuilder":
        """Add parallel fork node."""
        node = WorkflowNode(
            id=node_id or self._next_id("parallel"),
            name="Parallel Fork",
            node_type=NodeType.PARALLEL
        )
        self._workflow.nodes.append(node)
        return self
    
    def join(self, node_id: str | None = None) -> "WorkflowBuilder":
        """Add join node."""
        node = WorkflowNode(
            id=node_id or self._next_id("join"),
            name="Join",
            node_type=NodeType.JOIN
        )
        self._workflow.nodes.append(node)
        return self
    
    def edge(
        self,
        source: str,
        target: str,
        condition: str | None = None
    ) -> "WorkflowBuilder":
        """Add edge between nodes."""
        edge = WorkflowEdge(
            source=source,
            target=target,
            condition=condition
        )
        self._workflow.edges.append(edge)
        return self
    
    def chain(self, *node_ids: str) -> "WorkflowBuilder":
        """Chain nodes in sequence."""
        for i in range(len(node_ids) - 1):
            self.edge(node_ids[i], node_ids[i + 1])
        return self
    
    def build(self) -> WorkflowDefinition:
        """Build and validate workflow."""
        errors = self._workflow.validate()
        if errors:
            raise ValueError(f"Invalid workflow: {', '.join(errors)}")
        return self._workflow


class WorkflowExecutor:
    """High-level workflow executor."""
    
    def __init__(self, engine: WorkflowEngine | None = None):
        self.engine = engine or WorkflowEngine.instance()
    
    async def run(
        self,
        workflow: WorkflowDefinition,
        inputs: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Execute workflow and return results."""
        from tracing.tracer import Tracer
        from tracing.models import SpanType, SpanStatus
        
        tracer = Tracer.instance()
        span = tracer.start_span(
            SpanType.WORKFLOW,
            name=f"workflow_executor:{workflow.name}",
            input_data={"workflow": workflow.name}
        )
        
        try:
            # Register if not already
            if not self.engine.get(workflow.id):
                self.engine.register(workflow)
            
            # Execute
            run = await self.engine.execute(workflow.id, inputs)
            
            # Collect results
            results = {
                "run_id": run.id,
                "status": run.status,
                "context": run.context,
                "error": run.error
            }
            
            if run.status == "completed":
                tracer.end_span(span, status=SpanStatus.SUCCESS, output_data=results)
            else:
                tracer.end_span(span, status=SpanStatus.ERROR, error=run.error)
            
            return results
            
        except Exception as e:
            tracer.end_span(span, status=SpanStatus.ERROR, error=str(e))
            raise
    
    @staticmethod
    def builder(name: str, description: str = "") -> WorkflowBuilder:
        """Create workflow builder."""
        return WorkflowBuilder(name, description)
