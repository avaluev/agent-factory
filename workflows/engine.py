"""Workflow engine for DAG execution."""

import asyncio
from datetime import datetime
from typing import Any
import uuid

from workflows.models import (
    WorkflowDefinition, WorkflowNode, WorkflowRun,
    NodeType, NodeStatus
)


class WorkflowEngine:
    """Executes workflow DAGs with tracing."""
    
    _instance: "WorkflowEngine | None" = None
    
    def __init__(self):
        self._workflows: dict[str, WorkflowDefinition] = {}
        self._runs: dict[str, WorkflowRun] = {}
    
    @classmethod
    def instance(cls) -> "WorkflowEngine":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def reset(cls) -> None:
        """Reset singleton for testing."""
        cls._instance = None
    
    def register(self, workflow: WorkflowDefinition) -> None:
        """Register a workflow definition."""
        errors = workflow.validate()
        if errors:
            raise ValueError(f"Invalid workflow: {', '.join(errors)}")
        self._workflows[workflow.id] = workflow
    
    def get(self, workflow_id: str) -> WorkflowDefinition | None:
        """Get workflow by ID."""
        return self._workflows.get(workflow_id)
    
    async def execute(
        self,
        workflow_id: str,
        inputs: dict[str, Any] | None = None
    ) -> WorkflowRun:
        """Execute a workflow."""
        from tracing.tracer import Tracer
        from tracing.models import SpanType, SpanStatus
        
        tracer = Tracer.instance()
        span = tracer.start_span(
            SpanType.WORKFLOW,
            name=f"workflow:{workflow_id}",
            input_data={"workflow_id": workflow_id, "inputs": inputs}
        )
        
        try:
            workflow = self._workflows.get(workflow_id)
            if not workflow:
                raise ValueError(f"Workflow not found: {workflow_id}")
            
            # Create run
            run = WorkflowRun(
                id=str(uuid.uuid4())[:8],
                workflow_id=workflow_id,
                context=inputs or {}
            )
            self._runs[run.id] = run
            
            # Reset node states
            for node in workflow.nodes:
                node.status = NodeStatus.PENDING
                node.result = None
                node.error = None
            
            # Execute from start nodes
            start_nodes = workflow.get_start_nodes()
            await self._execute_nodes(workflow, run, start_nodes)
            
            # Determine final status
            failed_nodes = [n for n in workflow.nodes if n.status == NodeStatus.FAILED]
            if failed_nodes:
                run.status = "failed"
                run.error = f"Nodes failed: {[n.id for n in failed_nodes]}"
                tracer.end_span(span, status=SpanStatus.ERROR, error=run.error)
            else:
                run.status = "completed"
                tracer.end_span(span, status=SpanStatus.SUCCESS, output_data={
                    "run_id": run.id,
                    "status": run.status
                })
            
            run.completed_at = datetime.utcnow()
            return run
            
        except Exception as e:
            tracer.end_span(span, status=SpanStatus.ERROR, error=str(e))
            raise
    
    async def _execute_nodes(
        self,
        workflow: WorkflowDefinition,
        run: WorkflowRun,
        nodes: list[WorkflowNode]
    ) -> None:
        """Execute a list of nodes and their successors."""
        from tracing.tracer import Tracer
        from tracing.models import SpanType, SpanStatus
        
        tracer = Tracer.instance()
        
        for node in nodes:
            if node.status != NodeStatus.PENDING:
                continue
            
            # Check if all predecessors completed
            predecessors = workflow.get_predecessors(node.id)
            if not self._all_predecessors_done(workflow, predecessors):
                continue
            
            # Check conditional edges
            if not self._evaluate_conditions(workflow, run, node):
                node.status = NodeStatus.SKIPPED
                continue
            
            # Execute node
            span = tracer.start_span(
                SpanType.WORKFLOW,
                name=f"node:{node.id}",
                input_data={"node_type": node.node_type.value}
            )
            
            node.status = NodeStatus.RUNNING
            node.started_at = datetime.utcnow()
            
            try:
                if node.node_type == NodeType.START:
                    node.result = run.context
                    node.status = NodeStatus.COMPLETED
                    
                elif node.node_type == NodeType.END:
                    node.status = NodeStatus.COMPLETED
                    
                elif node.node_type == NodeType.TASK:
                    result = await self._execute_task(node, run.context)
                    node.result = result
                    if isinstance(result, dict):
                        run.context.update(result)
                    node.status = NodeStatus.COMPLETED
                    
                elif node.node_type == NodeType.PARALLEL:
                    node.status = NodeStatus.COMPLETED
                    
                elif node.node_type == NodeType.JOIN:
                    node.status = NodeStatus.COMPLETED
                    
                elif node.node_type == NodeType.DECISION:
                    node.status = NodeStatus.COMPLETED
                
                node.completed_at = datetime.utcnow()
                tracer.end_span(span, status=SpanStatus.SUCCESS, output_data={"status": node.status.value})
                
            except Exception as e:
                node.status = NodeStatus.FAILED
                node.error = str(e)
                node.completed_at = datetime.utcnow()
                tracer.end_span(span, status=SpanStatus.ERROR, error=str(e))
                
                # Check retry
                if node.retry_count > 0:
                    node.retry_count -= 1
                    node.status = NodeStatus.PENDING
                    await self._execute_nodes(workflow, run, [node])
                    return
        
        # Execute successors
        next_nodes = []
        for node in nodes:
            if node.status == NodeStatus.COMPLETED:
                successor_ids = workflow.get_successors(node.id)
                for sid in successor_ids:
                    succ_node = workflow.get_node(sid)
                    if succ_node and succ_node.status == NodeStatus.PENDING:
                        next_nodes.append(succ_node)
        
        if next_nodes:
            # Handle parallel execution
            parallel_groups = self._group_parallel_nodes(workflow, next_nodes)
            
            for group in parallel_groups:
                if len(group) > 1:
                    # Execute in parallel
                    await asyncio.gather(*[
                        self._execute_nodes(workflow, run, [n])
                        for n in group
                    ])
                else:
                    await self._execute_nodes(workflow, run, group)
    
    def _all_predecessors_done(
        self,
        workflow: WorkflowDefinition,
        predecessor_ids: list[str]
    ) -> bool:
        """Check if all predecessor nodes are done."""
        for pid in predecessor_ids:
            node = workflow.get_node(pid)
            if node and node.status not in [NodeStatus.COMPLETED, NodeStatus.SKIPPED]:
                return False
        return True
    
    def _evaluate_conditions(
        self,
        workflow: WorkflowDefinition,
        run: WorkflowRun,
        node: WorkflowNode
    ) -> bool:
        """Evaluate incoming edge conditions."""
        predecessors = workflow.get_predecessors(node.id)
        
        for pid in predecessors:
            edge = workflow.get_edge(pid, node.id)
            if edge and edge.condition:
                # Simple expression evaluation
                try:
                    result = eval(edge.condition, {"context": run.context})
                    if not result:
                        return False
                except Exception:
                    return False
        
        return True
    
    async def _execute_task(
        self,
        node: WorkflowNode,
        context: dict[str, Any]
    ) -> Any:
        """Execute a task node."""
        from core.tool_registry import ToolRegistry
        
        handler = node.handler
        
        if callable(handler):
            # Direct async function
            return await handler(context)
        elif isinstance(handler, str):
            # Tool name
            registry = ToolRegistry.instance()
            params = {**context, **node.config}
            return await registry.execute(handler, params)
        else:
            raise ValueError(f"Invalid handler for node {node.id}")
    
    def _group_parallel_nodes(
        self,
        workflow: WorkflowDefinition,
        nodes: list[WorkflowNode]
    ) -> list[list[WorkflowNode]]:
        """Group nodes that can execute in parallel."""
        # Simple grouping: nodes after PARALLEL node run together
        groups = []
        current_group = []
        
        for node in nodes:
            predecessors = workflow.get_predecessors(node.id)
            is_after_parallel = any(
                workflow.get_node(p) and 
                workflow.get_node(p).node_type == NodeType.PARALLEL
                for p in predecessors
            )
            
            if is_after_parallel:
                current_group.append(node)
            else:
                if current_group:
                    groups.append(current_group)
                    current_group = []
                groups.append([node])
        
        if current_group:
            groups.append(current_group)
        
        return groups if groups else [[n] for n in nodes]
    
    def get_run(self, run_id: str) -> WorkflowRun | None:
        """Get workflow run by ID."""
        return self._runs.get(run_id)
    
    def list_workflows(self) -> list[str]:
        """List registered workflow IDs."""
        return list(self._workflows.keys())
