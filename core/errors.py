"""Platform-wide exception hierarchy."""

class AgentPlatformError(Exception):
    """Base exception for all agent platform errors."""
    pass

class ModelProviderError(AgentPlatformError):
    """Error communicating with an LLM provider."""
    def __init__(self, provider: str, message: str, details: dict | None = None):
        self.provider = provider
        self.details = details or {}
        super().__init__(f"[{provider}] {message}")

class ToolExecutionError(AgentPlatformError):
    """Error during tool execution."""
    def __init__(self, tool_name: str, message: str, original_error: Exception | None = None):
        self.tool_name = tool_name
        self.original_error = original_error
        super().__init__(f"Tool '{tool_name}' failed: {message}")

class SkillLoadError(AgentPlatformError):
    """Error loading or executing a skill."""
    pass

class RAGError(AgentPlatformError):
    """Error in RAG pipeline."""
    pass

class WorkflowError(AgentPlatformError):
    """Error in workflow execution."""
    def __init__(self, workflow_id: str, step: str | None, message: str):
        self.workflow_id = workflow_id
        self.step = step
        super().__init__(f"Workflow '{workflow_id}' step '{step}': {message}")

class BudgetExceededError(AgentPlatformError):
    """Monthly token/cost budget exceeded."""
    pass
