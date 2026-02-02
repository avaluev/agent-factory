# Agent Factory 🤖

A comprehensive AI Agent Platform with tracing, RAG, memory, skills, and workflow orchestration.

## 🌟 Features

### Core Capabilities
- **🔍 Full Observability**: SQLite-based tracing with nested span tracking
- **🤖 ReAct Agent Loop**: Think → Act → Observe pattern with tool calling
- **📚 RAG System**: ChromaDB vector store with semantic search
- **🧠 Memory System**: Short-term, long-term, and episodic memory
- **⚡ Skills Framework**: Composable agent capabilities
- **📊 Workflow Engine**: DAG-based task orchestration
- **🎯 Smart Routing**: Cost-aware multi-LLM routing

### Supported Models
- **Local**: Ollama (zero cost)
- **Cloud**: Anthropic Claude, OpenAI

### Document Ingestion
Supports: PDF, DOCX, TXT, Markdown, CSV

## 🚀 Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/avaluev/agent-factory.git
cd agent-factory

# Set up Python environment
pyenv local 3.11.13  # or any Python 3.11+
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -e .
```

### Configuration

Create a `.env` file:

```bash
# Anthropic (optional, for cloud models)
ANTHROPIC_API_KEY=your_key_here

# OpenAI (optional, for embedding fallback)
OPENAI_API_KEY=your_key_here

# Ollama (local models)
OLLAMA_BASE_URL=http://localhost:11434
```

### Usage

```bash
# Start interactive agent session
agent run

# Ingest documents into knowledge base
agent ingest /path/to/documents

# List available skills
agent skills

# Check system status
agent status
```

## 📁 Project Structure

```
agent-platform/
├── core/              # Agent core (ReAct loop, tool registry, model adapters)
├── tracing/           # Observability (span tracking, trace storage)
├── rag/               # RAG system (embeddings, vector store, ingestion)
├── memory/            # Memory systems (short-term, long-term, episodic)
├── skills/            # Skills framework (loader, executor, builtin skills)
├── workflows/         # Workflow engine (DAG execution, checkpointing)
├── router/            # Multi-LLM routing (cost-aware strategies)
├── mcp/               # MCP integration
└── config/            # Configuration files
```

## 🏗️ Architecture

### Agent Loop
```
User Input → System Prompt + Context → LLM → Tool Calls → Execute Tools → Loop
```

### Tracing
Every operation creates spans:
- `agent_run` → `agent_iteration` → `llm_call` + `tool_call`
- Stored in SQLite with full I/O, tokens, cost

### RAG Pipeline
```
Documents → Load → Chunk → Embed (Ollama) → Store (ChromaDB) → Query → Context
```

### Memory Architecture
- **Short-term**: Sliding window conversation buffer
- **Long-term**: SQLite + vector semantic search
- **Episodic**: Task execution history with success/failure tracking

## 🛠️ Development

### Running Tests
```bash
pytest tests/
```

### Code Quality
```bash
# Type checking
mypy core/ rag/ memory/

# Linting
ruff check .
```

## 📊 Tracing & Observability

All operations are fully traced:

```python
from tracing import Tracer

tracer = Tracer.instance()

# Query recent traces
traces = tracer.store.get_recent_traces(limit=10)

# Get LLM cost summary
summary = tracer.store.get_llm_summary()
print(f"Total cost: ${summary['total_cost_usd']:.4f}")
```

## 🎯 Skills

Skills are composable capabilities:

```python
from skills import Skill, SkillResult, SkillStatus

class MySkill(Skill):
    def _default_metadata(self):
        return SkillMetadata(
            name="my_skill",
            version="1.0.0",
            description="Does something useful"
        )
    
    async def execute(self, inputs):
        # Your logic here
        return SkillResult(
            status=SkillStatus.SUCCESS,
            output={"result": "done"}
        )
```

## 📝 Workflows

Define DAG workflows:

```python
from workflows import WorkflowDefinition, WorkflowNode

workflow = WorkflowDefinition(
    name="data_pipeline",
    nodes=[
        WorkflowNode(id="ingest", task="ingest_data"),
        WorkflowNode(id="process", task="process_data", depends_on=["ingest"]),
        WorkflowNode(id="analyze", task="analyze_results", depends_on=["process"])
    ]
)
```

## 🤝 Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## 📄 License

MIT License - see LICENSE file for details

## 🙏 Acknowledgments

Built with:
- [Anthropic Claude](https://www.anthropic.com/) - AI reasoning
- [Ollama](https://ollama.ai/) - Local model inference
- [ChromaDB](https://www.trychroma.com/) - Vector database
- [FastAPI](https://fastapi.tiangolo.com/) - API framework
- [Typer](https://typer.tiangolo.com/) - CLI framework

---

**Agent Factory** - Build intelligent, observable, and composable AI agents 🚀
