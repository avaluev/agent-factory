# Agent Factory - Development Guide

## Knowledge Base for LLM Development

This guide covers extending the Agent Factory for LLM-powered development workflows.

---

## Table of Contents

1. [Development Setup](#development-setup)
2. [Creating Custom Skills](#creating-custom-skills)
3. [LLM Integration Patterns](#llm-integration-patterns)
4. [Knowledge Base Design](#knowledge-base-design)
5. [Commit Workflow](#commit-workflow)
6. [Testing](#testing)
7. [Performance Optimization](#performance-optimization)

---

## Development Setup

### Local Environment

```bash
# Clone repository
cd ~/projects
git clone https://github.com/avaluev/agent-factory.git agent-platform
cd agent-platform

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install development dependencies
pip install -r requirements-dev.txt  # pytest, black, mypy, etc.

# Set up pre-commit hooks
pre-commit install
```

### Environment Variables

Create `.env` for development:
```bash
# API Keys
ANTHROPIC_API_KEY=sk-ant-api03-...
OPENAI_API_KEY=sk-...

# Models
DEFAULT_MODEL=claude-sonnet-4-5-20250929
OLLAMA_BASE_URL=http://localhost:11434

# Development
LOG_LEVEL=DEBUG
ENABLE_TRACING=true
DATABASE_PATH=./data/dev/

# Testing
TEST_MODE=true
MOCK_LLM=false
```

### Directory Structure

```
agent-platform/
├── core/                   # Core agent logic
│   ├── agent.py           # ReAct agent loop
│   ├── factory.py         # System builder
│   ├── models/            # LLM adapters
│   │   ├── base.py
│   │   ├── anthropic_adapter.py
│   │   └── ollama_adapter.py
│   ├── tool_registry.py   # Tool management
│   └── dev_tools.py       # Development utilities
│
├── skills/                # Skill system
│   ├── base.py           # Base classes
│   ├── registry.py       # Auto-discovery
│   ├── executor.py       # Execution engine
│   └── builtin/          # Built-in skills
│       ├── project_planner/
│       ├── code_reviewer/  # (your custom skill)
│       └── ...
│
├── memory/               # Memory systems
│   ├── manager.py
│   ├── long_term.py      # SQLite + ChromaDB
│   ├── episodic.py       # Task history
│   └── short_term.py     # Conversation buffer
│
├── tracing/              # Observability
│   ├── tracer.py
│   └── models.py
│
├── workflows/            # Multi-agent workflows
│   └── orchestrator.py
│
├── tests/                # Test suite
│   ├── unit/
│   ├── integration/
│   └── e2e/
│
└── docs/                 # Documentation
    ├── FACTORY_GUIDE.md
    ├── DEVELOPMENT_GUIDE.md  # This file
    └── API.md
```

---

## Creating Custom Skills

Skills are self-contained capabilities that agents can invoke. Each skill has:
- **Metadata**: Name, version, description, inputs/outputs
- **Execute Method**: Core logic
- **Error Handling**: Graceful failure modes

### Skill Template

```python
# skills/builtin/my_skill/skill.py

from skills.base import Skill, SkillMetadata, SkillResult, SkillStatus
from typing import Any
from datetime import datetime

class MySkill(Skill):
    """
    Brief description of what this skill does.

    Example:
        skill = MySkill()
        result = await skill.execute({"input": "value"})
    """

    def _default_metadata(self) -> SkillMetadata:
        """Define skill metadata."""
        return SkillMetadata(
            name="my_skill",
            version="1.0.0",
            description="One-line description for LLM to understand when to use this",
            author="Your Name",
            tags=["category", "keywords"],
            inputs={
                "type": "object",
                "properties": {
                    "required_param": {
                        "type": "string",
                        "description": "What this parameter does"
                    },
                    "optional_param": {
                        "type": "integer",
                        "default": 42,
                        "description": "Optional parameter with default"
                    }
                },
                "required": ["required_param"]
            },
            outputs={
                "type": "object",
                "properties": {
                    "result": {"type": "string"},
                    "metadata": {"type": "object"}
                }
            }
        )

    async def execute(self, inputs: dict[str, Any]) -> SkillResult:
        """
        Execute the skill.

        Args:
            inputs: Dict matching the schema defined in metadata

        Returns:
            SkillResult with status, output, and optional error
        """
        from tracing.tracer import Tracer
        from tracing.models import SpanType, SpanStatus

        # Always trace skill execution
        tracer = Tracer.instance()
        span = tracer.start_span(
            SpanType.SKILL,
            name=f"{self.metadata.name}_execute",
            input_data={"inputs": inputs}
        )

        start_time = datetime.utcnow()

        try:
            # Extract and validate inputs
            required_param = inputs["required_param"]
            optional_param = inputs.get("optional_param", 42)

            # Your logic here
            result = self._do_work(required_param, optional_param)

            # Calculate execution time
            execution_time = (datetime.utcnow() - start_time).total_seconds()

            # End trace span
            tracer.end_span(span, status=SpanStatus.SUCCESS, output_data={
                "result_preview": str(result)[:200],
                "execution_time": execution_time
            })

            return SkillResult(
                status=SkillStatus.SUCCESS,
                output={
                    "result": result,
                    "metadata": {
                        "execution_time": execution_time,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                },
                execution_time=execution_time
            )

        except KeyError as e:
            # Missing required input
            error_msg = f"Missing required input: {e}"
            tracer.end_span(span, status=SpanStatus.ERROR, error=error_msg)
            return SkillResult(
                status=SkillStatus.FAILURE,
                error=error_msg,
                execution_time=(datetime.utcnow() - start_time).total_seconds()
            )

        except Exception as e:
            # Unexpected error
            error_msg = f"Skill execution failed: {str(e)}"
            tracer.end_span(span, status=SpanStatus.ERROR, error=error_msg)
            return SkillResult(
                status=SkillStatus.FAILURE,
                error=error_msg,
                execution_time=(datetime.utcnow() - start_time).total_seconds()
            )

    def _do_work(self, param1: str, param2: int) -> Any:
        """Internal helper method."""
        # Your implementation here
        return {"processed": param1, "count": param2}
```

### Skill Registration

**`skills/builtin/my_skill/__init__.py`:**
```python
from skills.builtin.my_skill.skill import MySkill

__all__ = ["MySkill"]
```

**`skills/builtin/my_skill/SKILL.md`:**
```markdown
# My Skill

One-line description.

## Purpose

Detailed explanation of what this skill does and when to use it.

## Inputs

- `required_param` (string, required): Description
- `optional_param` (integer, optional, default=42): Description

## Outputs

- `result` (string): Description of output
- `metadata` (object): Execution metadata

## Examples

### Example 1: Basic Usage
```python
skill = MySkill()
result = await skill.execute({
    "required_param": "hello"
})
```

### Example 2: With Optional Params
```python
result = await skill.execute({
    "required_param": "hello",
    "optional_param": 100
})
```

## Error Handling

- Returns `FAILURE` status if required inputs missing
- Returns `PARTIAL` status if some operations succeed
- Logs all errors to tracing system

## Performance

- Typical execution time: < 100ms
- Memory usage: < 50MB
- Rate limits: None

## Dependencies

- None (or list external dependencies)
```

---

## LLM Integration Patterns

### Pattern 1: Single LLM Call

Simple prompt → response pattern:

```python
from core.agent import Agent
from core.models.anthropic_adapter import AnthropicAdapter

async def simple_llm_call(prompt: str) -> str:
    """Single LLM call with prompt."""
    agent = Agent(model_adapter=AnthropicAdapter())
    response = await agent.run(prompt)
    return response
```

### Pattern 2: Structured Output

Force JSON output with validation:

```python
from core.models.base import ChatMessage, MessageRole
from core.models.anthropic_adapter import AnthropicAdapter
import json

async def structured_llm_call(prompt: str) -> dict:
    """LLM call expecting JSON output."""
    adapter = AnthropicAdapter(model="claude-sonnet-4-5-20250929")

    messages = [
        ChatMessage(role=MessageRole.USER, content=f"""{prompt}

IMPORTANT: Respond with ONLY valid JSON, no markdown, no explanations.

Output format:
{{
  "field1": "value1",
  "field2": "value2"
}}""")
    ]

    response = await adapter.chat(
        messages=messages,
        temperature=0.7,
        max_tokens=4096
    )

    # Parse JSON
    try:
        return json.loads(response.content)
    except json.JSONDecodeError:
        # Fallback: extract JSON from text
        import re
        json_match = re.search(r'\{.*\}', response.content, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(0))
        raise ValueError("LLM did not return valid JSON")
```

### Pattern 3: Multi-Step Reasoning

Break complex tasks into steps:

```python
async def multi_step_reasoning(task: str) -> dict:
    """Multi-step LLM reasoning with intermediate results."""
    adapter = AnthropicAdapter()
    results = {}

    # Step 1: Analyze
    messages = [
        ChatMessage(role=MessageRole.USER, content=f"Analyze this task: {task}")
    ]
    analysis = await adapter.chat(messages=messages)
    results["analysis"] = analysis.content

    # Step 2: Plan (using previous result)
    messages.append(ChatMessage(role=MessageRole.ASSISTANT, content=analysis.content))
    messages.append(ChatMessage(
        role=MessageRole.USER,
        content="Based on your analysis, create a step-by-step plan."
    ))
    plan = await adapter.chat(messages=messages)
    results["plan"] = plan.content

    # Step 3: Execute (conceptually)
    messages.append(ChatMessage(role=MessageRole.ASSISTANT, content=plan.content))
    messages.append(ChatMessage(
        role=MessageRole.USER,
        content="Now execute the plan and provide results."
    ))
    execution = await adapter.chat(messages=messages)
    results["execution"] = execution.content

    return results
```

### Pattern 4: Tool-Using Agent

Let agent use tools to accomplish tasks:

```python
from core.agent import Agent
from core.tool_registry import ToolRegistry

async def agent_with_tools(task: str) -> str:
    """Agent that can use registered tools."""
    # Tools are automatically available from ToolRegistry
    agent = Agent(model_adapter=AnthropicAdapter())

    # Agent will decide which tools to use
    result = await agent.run(task)
    return result
```

### Pattern 5: RAG (Retrieval-Augmented Generation)

Combine knowledge base with LLM:

```python
from rag.query import RAGEngine

async def rag_query(question: str, collection: str = "default") -> str:
    """Query with retrieved context."""
    rag = RAGEngine.instance()

    # Retrieve relevant context
    context_docs = await rag.query(
        query=question,
        collection=collection,
        top_k=5
    )

    # Build prompt with context
    context_text = "\n\n".join([doc["content"] for doc in context_docs])

    prompt = f"""Answer the question using the provided context.

Context:
{context_text}

Question: {question}

Answer:"""

    # Get LLM response
    agent = Agent(model_adapter=AnthropicAdapter())
    response = await agent.run(prompt)
    return response
```

---

## Knowledge Base Design

### ChromaDB Collections

Organize knowledge by domain:

```python
from rag.ingestion import RAGIngestion

# Define collections
COLLECTIONS = {
    "project_plans": "Implementation plans from factory",
    "code_examples": "Code snippets and patterns",
    "documentation": "Technical documentation",
    "conversations": "Chat history and Q&A",
    "decisions": "Architectural decisions and rationale"
}

# Ingest knowledge
async def setup_knowledge_base():
    rag = RAGIngestion.instance()

    # Ingest project documentation
    await rag.ingest_directory(
        directory="~/projects/docs",
        collection="documentation",
        metadata={"source": "docs", "type": "markdown"}
    )

    # Ingest code examples
    await rag.ingest_directory(
        directory="~/projects/examples",
        collection="code_examples",
        metadata={"source": "examples", "language": "python"}
    )
```

### Metadata Schema

Consistent metadata for effective retrieval:

```python
METADATA_SCHEMA = {
    "source": str,          # File path or URL
    "type": str,            # markdown, code, chat, etc.
    "language": str,        # python, javascript, etc.
    "author": str,          # Creator
    "created_at": str,      # ISO timestamp
    "tags": list[str],      # ["api", "authentication", etc.]
    "importance": float,    # 0.0-1.0
    "domain": str,          # "backend", "frontend", etc.
}
```

### Query Patterns

**Semantic Search:**
```python
results = await rag.query(
    query="How do I implement JWT authentication?",
    collection="documentation",
    top_k=5,
    metadata_filter={"domain": "backend"}
)
```

**Hybrid Search (semantic + keyword):**
```python
results = await rag.hybrid_query(
    query="FastAPI async endpoints",
    keywords=["fastapi", "async", "await"],
    collection="code_examples",
    top_k=10
)
```

---

## Commit Workflow

### Git Hooks

The factory uses pre-commit hooks for code quality:

**`.pre-commit-config.yaml`:**
```yaml
repos:
  - repo: https://github.com/psf/black
    rev: 23.3.0
    hooks:
      - id: black
        language_version: python3.11

  - repo: https://github.com/pycqa/isort
    rev: 5.12.0
    hooks:
      - id: isort
        args: ["--profile", "black"]

  - repo: https://github.com/pycqa/flake8
    rev: 6.0.0
    hooks:
      - id: flake8
        args: ["--max-line-length=100", "--ignore=E203,W503"]

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.3.0
    hooks:
      - id: mypy
        additional_dependencies: [types-all]
```

### Commit Message Format

Follow conventional commits:

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation
- `style`: Formatting
- `refactor`: Code restructuring
- `test`: Adding tests
- `chore`: Maintenance

**Examples:**
```bash
git commit -m "feat(skills): add code review skill"
git commit -m "fix(factory): handle incomplete JSON responses"
git commit -m "docs(guide): add LLM integration patterns"
```

### CI/CD Pipeline

GitHub Actions workflow:

**`.github/workflows/ci.yml`:**
```yaml
name: CI

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: pip install -r requirements-dev.txt
      - run: pytest tests/ --cov=core --cov=skills
      - run: black --check .
      - run: mypy core/ skills/
```

---

## Testing

### Unit Tests

Test individual components:

```python
# tests/unit/test_project_planner.py

import pytest
from skills.builtin.project_planner.skill import ProjectPlannerSkill

@pytest.mark.asyncio
async def test_project_planner_basic():
    """Test basic planning functionality."""
    skill = ProjectPlannerSkill()

    result = await skill.execute({
        "idea": "Simple todo app with React",
        "detail_level": "low"
    })

    assert result.status == "success"
    assert "tasks" in result.output
    assert len(result.output["tasks"]) >= 5
    assert result.output["plan"]["tech_stack"]
```

### Integration Tests

Test component interactions:

```python
# tests/integration/test_factory_flow.py

@pytest.mark.asyncio
async def test_factory_end_to_end():
    """Test complete factory workflow."""
    from core.factory import SystemBuilderFactory

    factory = SystemBuilderFactory.instance()

    project = await factory.create_from_idea(
        idea="Blog platform with React and FastAPI",
        detail_level="medium"
    )

    assert project.status == "planning"
    assert len(project.tasks) >= 10
    assert project.plan["tech_stack"]
```

### Mocking LLM Calls

For deterministic tests:

```python
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_with_mocked_llm():
    """Test with mocked LLM responses."""
    mock_response = {
        "overview": "Test project",
        "tech_stack": ["Python", "FastAPI"],
        "tasks": [
            {"id": "task_1", "title": "Setup", "description": "Initialize project"}
        ]
    }

    with patch('core.models.anthropic_adapter.AnthropicAdapter.chat') as mock:
        mock.return_value = AsyncMock(content=json.dumps(mock_response))

        skill = ProjectPlannerSkill()
        result = await skill.execute({"idea": "test", "detail_level": "low"})

        assert result.status == "success"
```

---

## Performance Optimization

### Token Usage

Monitor and optimize token consumption:

```python
from tracing.tracer import Tracer

# Query token usage
tracer = Tracer.instance()
import sqlite3

conn = sqlite3.connect("data/traces.db")
cursor = conn.cursor()

# Total tokens by model
cursor.execute("""
    SELECT model, SUM(input_tokens), SUM(output_tokens), SUM(cost_usd)
    FROM traces
    WHERE span_type = 'llm_call'
    GROUP BY model
""")

for row in cursor.fetchall():
    print(f"Model: {row[0]}, Input: {row[1]}, Output: {row[2]}, Cost: ${row[3]:.2f}")
```

### Caching Strategies

Cache expensive LLM calls:

```python
import hashlib
import json
from functools import lru_cache

# In-memory cache for session
@lru_cache(maxsize=128)
def get_cached_response(prompt_hash: str) -> str:
    """Cache LLM responses by prompt hash."""
    return CACHE.get(prompt_hash)

async def cached_llm_call(prompt: str) -> str:
    """LLM call with caching."""
    # Hash prompt
    prompt_hash = hashlib.md5(prompt.encode()).hexdigest()

    # Check cache
    cached = get_cached_response(prompt_hash)
    if cached:
        return cached

    # Call LLM
    response = await llm_call(prompt)

    # Store in cache
    CACHE[prompt_hash] = response
    return response
```

### Batch Processing

Process multiple items efficiently:

```python
async def batch_llm_calls(prompts: list[str], batch_size: int = 5) -> list[str]:
    """Process multiple prompts in batches."""
    import asyncio

    results = []
    for i in range(0, len(prompts), batch_size):
        batch = prompts[i:i + batch_size]

        # Execute batch concurrently
        batch_results = await asyncio.gather(*[
            llm_call(prompt) for prompt in batch
        ])

        results.extend(batch_results)

    return results
```

---

## Next Steps

1. **Build Career Automation System**: Apply these patterns to implement the system
2. **Add Domain Skills**: Create career-specific skills (resume parsing, skill extraction, etc.)
3. **Extend Knowledge Base**: Ingest career industry knowledge
4. **Monitor Production**: Set up logging and alerting

---

**Last Updated:** 2026-02-02
**Version:** 1.0.0
