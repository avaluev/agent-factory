"""Development tools for autonomous system building."""

import os
import subprocess
from pathlib import Path
from core.tool_registry import ToolRegistry, ToolSchema


def register_dev_tools() -> None:
    """Register development tools with the tool registry."""
    registry = ToolRegistry.instance()
    
    # Write file tool
    async def write_file_tool(path: str, content: str, mode: str = "w") -> dict:
        """Write content to a file."""
        try:
            file_path = Path(path)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(file_path, mode, encoding="utf-8") as f:
                f.write(content)
            
            return {
                "success": True,
                "path": str(file_path),
                "size": len(content),
                "message": f"File written: {path}"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    registry.register(ToolSchema(
        name="write_file",
        description="Write content to a file. Creates parent directories if needed. Use for creating new code files, configs, docs.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path (relative or absolute)"},
                "content": {"type": "string", "description": "File content to write"},
                "mode": {"type": "string", "enum": ["w", "a"], "default": "w", "description": "Write mode: 'w' (overwrite) or 'a' (append)"}
            },
            "required": ["path", "content"]
        },
        handler=write_file_tool,
        category="development",
        cost_tier="free"
    ))
    
    # Create directory tool
    async def create_directory_tool(path: str) -> dict:
        """Create a directory."""
        try:
            dir_path = Path(path)
            dir_path.mkdir(parents=True, exist_ok=True)
            return {
                "success": True,
                "path": str(dir_path),
                "message": f"Directory created: {path}"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    registry.register(ToolSchema(
        name="create_directory",
        description="Create a directory and all parent directories. Useful for setting up project structure.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path to create"}
            },
            "required": ["path"]
        },
        handler=create_directory_tool,
        category="development",
        cost_tier="free"
    ))
    
    # Execute shell command tool
    async def execute_command_tool(command: str, working_dir: str = ".") -> dict:
        """Execute a shell command."""
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=working_dir,
                capture_output=True,
                text=True,
                timeout=120
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
                "command": command
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Command timed out (120s limit)"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    registry.register(ToolSchema(
        name="execute_command",
        description="Execute a shell command. Use for: npm/pip install, git operations, build commands, tests. Has 120s timeout.",
        parameters={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to execute"},
                "working_dir": {"type": "string", "default": ".", "description": "Working directory for command"}
            },
            "required": ["command"]
        },
        handler=execute_command_tool,
        category="development",
        cost_tier="free"
    ))
    
    # File exists check tool
    async def file_exists_tool(path: str) -> dict:
        """Check if a file or directory exists."""
        path_obj = Path(path)
        return {
            "exists": path_obj.exists(),
            "is_file": path_obj.is_file() if path_obj.exists() else False,
            "is_dir": path_obj.is_dir() if path_obj.exists() else False,
            "path": str(path_obj.absolute())
        }
    
    registry.register(ToolSchema(
        name="file_exists",
        description="Check if a file or directory exists. Returns existence status and type (file/dir).",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to check"}
            },
            "required": ["path"]
        },
        handler=file_exists_tool,
        category="development",
        cost_tier="free"
    ))
    
    print("✓ Registered development tools: write_file, create_directory, execute_command, file_exists")
