"""Skill loader for discovering and loading skills."""

import os
import importlib
import importlib.util
from pathlib import Path
from typing import Any

import yaml

from skills.base import Skill, SkillMetadata


class SkillLoader:
    """Discovers and loads skills from directories."""
    
    _instance: "SkillLoader | None" = None
    
    def __init__(self, skill_dirs: list[str] | None = None):
        self.skill_dirs = skill_dirs or [
            os.getenv("SKILLS_DIR", str(Path.home() / ".agent-platform" / "skills")),
            str(Path(__file__).parent / "builtin")
        ]
        self._skills: dict[str, type[Skill]] = {}
        self._metadata_cache: dict[str, SkillMetadata] = {}
    
    @classmethod
    def instance(cls) -> "SkillLoader":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def reset(cls) -> None:
        """Reset singleton for testing."""
        cls._instance = None
    
    def discover(self) -> dict[str, SkillMetadata]:
        """Discover all available skills."""
        from tracing.tracer import Tracer
        from tracing.models import SpanType, SpanStatus
        
        tracer = Tracer.instance()
        span = tracer.start_span(
            SpanType.SKILL,
            name="skill_discovery",
            input_data={"dirs": self.skill_dirs}
        )
        
        try:
            discovered = {}
            
            for skill_dir in self.skill_dirs:
                dir_path = Path(skill_dir)
                if not dir_path.exists():
                    continue
                
                # Look for SKILL.md or skill.yaml files
                for skill_path in dir_path.iterdir():
                    if skill_path.is_dir():
                        metadata = self._load_skill_metadata(skill_path)
                        if metadata:
                            discovered[metadata.name] = metadata
                            self._metadata_cache[metadata.name] = metadata
            
            tracer.end_span(span, status=SpanStatus.SUCCESS, output_data={
                "discovered_count": len(discovered)
            })
            return discovered
            
        except Exception as e:
            tracer.end_span(span, status=SpanStatus.ERROR, error=str(e))
            raise
    
    def _load_skill_metadata(self, skill_path: Path) -> SkillMetadata | None:
        """Load skill metadata from directory."""
        # Try SKILL.md first
        skill_md = skill_path / "SKILL.md"
        if skill_md.exists():
            return self._parse_skill_md(skill_md)
        
        # Try skill.yaml
        skill_yaml = skill_path / "skill.yaml"
        if skill_yaml.exists():
            return self._parse_skill_yaml(skill_yaml)
        
        return None
    
    def _parse_skill_md(self, path: Path) -> SkillMetadata:
        """Parse SKILL.md format."""
        content = path.read_text()
        
        # Extract YAML frontmatter if present
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                frontmatter = yaml.safe_load(parts[1])
                return SkillMetadata.from_dict(frontmatter)
        
        # Fallback: extract from markdown headers
        name = path.parent.name
        description = ""
        
        for line in content.split("\n"):
            if line.startswith("# "):
                name = line[2:].strip()
            elif line.startswith("## Description"):
                continue
            elif description == "" and line.strip() and not line.startswith("#"):
                description = line.strip()
                break
        
        return SkillMetadata(
            name=name,
            version="1.0.0",
            description=description
        )
    
    def _parse_skill_yaml(self, path: Path) -> SkillMetadata:
        """Parse skill.yaml format."""
        with open(path) as f:
            data = yaml.safe_load(f)
        return SkillMetadata.from_dict(data)
    
    def load(self, skill_name: str) -> Skill:
        """Load and instantiate a skill by name."""
        from tracing.tracer import Tracer
        from tracing.models import SpanType, SpanStatus
        
        tracer = Tracer.instance()
        span = tracer.start_span(
            SpanType.SKILL,
            name=f"skill_load:{skill_name}",
            input_data={"skill_name": skill_name}
        )
        
        try:
            # Check cache
            if skill_name in self._skills:
                skill_class = self._skills[skill_name]
                tracer.end_span(span, status=SpanStatus.SUCCESS, output_data={"cached": True})
                return skill_class()
            
            # Find skill directory
            skill_path = self._find_skill_path(skill_name)
            if not skill_path:
                raise ValueError(f"Skill not found: {skill_name}")
            
            # Load skill module
            skill_class = self._load_skill_module(skill_path, skill_name)
            self._skills[skill_name] = skill_class
            
            tracer.end_span(span, status=SpanStatus.SUCCESS, output_data={"loaded": True})
            return skill_class()
            
        except Exception as e:
            tracer.end_span(span, status=SpanStatus.ERROR, error=str(e))
            raise
    
    def _find_skill_path(self, skill_name: str) -> Path | None:
        """Find skill directory by name."""
        for skill_dir in self.skill_dirs:
            path = Path(skill_dir) / skill_name
            if path.exists():
                return path
        return None
    
    def _load_skill_module(self, skill_path: Path, skill_name: str) -> type[Skill]:
        """Load skill module from path."""
        # Look for skill.py or __init__.py
        module_file = skill_path / "skill.py"
        if not module_file.exists():
            module_file = skill_path / "__init__.py"
        
        if not module_file.exists():
            raise ValueError(f"No skill module found in {skill_path}")
        
        # Load module
        spec = importlib.util.spec_from_file_location(
            f"skills.{skill_name}",
            module_file
        )
        if not spec or not spec.loader:
            raise ValueError(f"Failed to load skill module: {module_file}")
        
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        # Find Skill subclass
        for name in dir(module):
            obj = getattr(module, name)
            if (
                isinstance(obj, type) and 
                issubclass(obj, Skill) and 
                obj is not Skill
            ):
                return obj
        
        raise ValueError(f"No Skill class found in {module_file}")
    
    def get_metadata(self, skill_name: str) -> SkillMetadata | None:
        """Get metadata for a skill."""
        if skill_name not in self._metadata_cache:
            self.discover()
        return self._metadata_cache.get(skill_name)
    
    def list_skills(self) -> list[str]:
        """List all available skill names."""
        if not self._metadata_cache:
            self.discover()
        return list(self._metadata_cache.keys())
