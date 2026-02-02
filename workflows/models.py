"""Workflow data models."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Awaitable
from enum import Enum


class NodeType(Enum):
    """Type of workflow node."""
    TASK = "task"           # Execute a task/tool
    DECISION = "decision"   # Conditional branching
    PARALLEL = "parallel"   # Parallel execution fork
    JOIN = "join"           # Wait for parallel branches
    START = "start"         # Workflow entry point
    END = "end"             # Workflow exit point


class NodeStatus(Enum):
    """Execution status of a node."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class WorkflowNode:
    """Single node in workflow DAG."""
    id: str
    name: str
    node_type: NodeType
    handler: str | Callable[..., Awaitable[Any]] | None = None  # Tool name or async function
    config: dict[str, Any] = field(default_factory=dict)
    retry_count: int = 0
    timeout: float | None = None
    
    # Runtime state
    status: NodeStatus = NodeStatus.PENDING
    result: Any = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


@dataclass
class WorkflowEdge:
    """Edge connecting workflow nodes."""
    source: str  # Node ID
    target: str  # Node ID
    condition: str | None = None  # Expression for conditional edges


@dataclass
class WorkflowDefinition:
    """Complete workflow definition."""
    id: str
    name: str
    description: str = ""
    nodes: list[WorkflowNode] = field(default_factory=list)
    edges: list[WorkflowEdge] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def get_node(self, node_id: str) -> WorkflowNode | None:
        """Get node by ID."""
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None
    
    def get_start_nodes(self) -> list[WorkflowNode]:
        """Get entry point nodes."""
        return [n for n in self.nodes if n.node_type == NodeType.START]
    
    def get_end_nodes(self) -> list[WorkflowNode]:
        """Get exit point nodes."""
        return [n for n in self.nodes if n.node_type == NodeType.END]
    
    def get_successors(self, node_id: str) -> list[str]:
        """Get successor node IDs."""
        return [e.target for e in self.edges if e.source == node_id]
    
    def get_predecessors(self, node_id: str) -> list[str]:
        """Get predecessor node IDs."""
        return [e.source for e in self.edges if e.target == node_id]
    
    def get_edge(self, source: str, target: str) -> WorkflowEdge | None:
        """Get edge between two nodes."""
        for edge in self.edges:
            if edge.source == source and edge.target == target:
                return edge
        return None
    
    def validate(self) -> list[str]:
        """Validate workflow definition. Returns list of errors."""
        errors = []
        
        # Check for start/end nodes
        if not self.get_start_nodes():
            errors.append("Workflow must have at least one START node")
        if not self.get_end_nodes():
            errors.append("Workflow must have at least one END node")
        
        # Check all edge references exist
        node_ids = {n.id for n in self.nodes}
        for edge in self.edges:
            if edge.source not in node_ids:
                errors.append(f"Edge source '{edge.source}' not found")
            if edge.target not in node_ids:
                errors.append(f"Edge target '{edge.target}' not found")
        
        # Check for cycles (simple DFS)
        if self._has_cycle():
            errors.append("Workflow contains a cycle")
        
        return errors
    
    def _has_cycle(self) -> bool:
        """Check if workflow has cycles."""
        visited = set()
        rec_stack = set()
        
        def dfs(node_id: str) -> bool:
            visited.add(node_id)
            rec_stack.add(node_id)
            
            for succ in self.get_successors(node_id):
                if succ not in visited:
                    if dfs(succ):
                        return True
                elif succ in rec_stack:
                    return True
            
            rec_stack.remove(node_id)
            return False
        
        for node in self.nodes:
            if node.id not in visited:
                if dfs(node.id):
                    return True
        
        return False


@dataclass
class WorkflowRun:
    """Runtime state of a workflow execution."""
    id: str
    workflow_id: str
    status: str = "running"  # running, completed, failed, cancelled
    context: dict[str, Any] = field(default_factory=dict)
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    error: str | None = None
