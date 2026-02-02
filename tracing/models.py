"""
Trace data models.

A TraceSpan is one unit of observable work. Spans form trees:
  agent_run
  ├── agent_iteration (1)
  │   ├── routing_decision
  │   ├── llm_call         ← captures full prompt + response + tokens + cost
  │   └── tool_call        ← captures tool name + params + output
  │       └── rag_query    ← nested inside tool_call when agent calls rag_query
  ├── agent_iteration (2)
  │   └── llm_call
  └── ...

trace_id groups all spans belonging to one top-level operation.
parent_id links children to parents.
"""
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class SpanType(str, Enum):
    # Top-level
    AGENT_RUN = "agent_run"
    WORKFLOW_RUN = "workflow_run"

    # Agent internals
    AGENT_ITERATION = "agent_iteration"
    ROUTING_DECISION = "routing_decision"

    # LLM
    LLM_CALL = "llm_call"
    EMBEDDING = "embedding"

    # Tools & Skills
    TOOL_CALL = "tool_call"
    SKILL = "skill"
    SKILL_LOAD = "skill_load"
    SKILL_SCRIPT = "skill_script"

    # RAG
    RAG_INGEST = "rag_ingest"
    RAG_QUERY = "rag_query"

    # Memory
    MEMORY_OP = "memory_op"

    # Workflow
    WORKFLOW_STEP = "workflow_step"

    # External
    MCP_CALL = "mcp_call"


class SpanStatus(str, Enum):
    PENDING = "pending"
    SUCCESS = "success"
    ERROR = "error"


@dataclass
class TraceSpan:
    """One observable unit of work."""
    # Identity
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    parent_id: str | None = None
    trace_id: str | None = None

    # What
    span_type: SpanType = SpanType.TOOL_CALL
    name: str = ""

    # When
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    ended_at: str | None = None
    duration_ms: float = 0.0

    # Status
    status: SpanStatus = SpanStatus.PENDING
    error: str | None = None

    # Payload — what went in and what came out
    input_data: dict = field(default_factory=dict)
    output_data: dict = field(default_factory=dict)

    # LLM-specific fields (populated for llm_call spans)
    model: str | None = None
    provider: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0

    # Decision-specific (populated for routing_decision spans)
    decision_reasoning: str | None = None
