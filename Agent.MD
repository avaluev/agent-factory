---
name: agent-platform
version: 0.1.0
description: Self-developing AI agent platform with multi-provider routing, RAG, skills, and workflow orchestration. Processes raw user inputs to autonomously build agent-based solutions.
author: aleksandr
created: 2025-02-01
---

# Agent Platform — Master Specification

## Platform Identity
- Name: Agent Platform
- Purpose: Autonomous agent development and execution platform
- Philosophy: Bootstrap-first, cost-optimized, locally-first with cloud scale path

## Core Capabilities
1. **Input Processing**: Accepts markdown, CSV, DOCX, TXT, audio transcripts, conversation dumps
2. **Intent Understanding**: Extracts user goals, constraints, and context from raw inputs via RAG
3. **Autonomous Planning**: Generates implementation plans requiring human approval before execution
4. **Agent Development**: Creates and deploys agent workflows, skills, and integrations
5. **Multi-Provider LLM Routing**: Routes to cheapest viable model (local → cheap API → premium API)
6. **Skill Management**: Discovers, loads, and executes AgentSkills (SKILL.md standard)
7. **Memory System**: Short-term (context), long-term (semantic), episodic (history)
8. **RAG System**: Local document ingestion with ChromaDB + Ollama embeddings
9. **MCP Integration**: Connects to external tools via Model Context Protocol
10. **Workflow Orchestration**: DAG-based multi-step workflow execution with checkpointing

## Model Routing Priority
1. Local Ollama (qwen2.5-coder:14b, deepseek-coder-v2:16b) — $0
2. Gemini Flash / Deepseek API — budget tier
3. Claude Sonnet / GPT-4o — quality tier (final outputs only)

## Key Design Rules
- All data stays local by default
- Human approval gate before any execution phase
- Every operation is logged with cost tracking
- Skills follow Anthropic's SKILL.md standard (agentskills.io)
- Workflows are defined as YAML, executed as DAGs
- Memory consolidation runs after every 10 interactions

## File Conventions
- All Python files include type hints
- All modules include docstrings
- Configuration via .env (never hardcoded)
- Tests mirror source structure under tests/
