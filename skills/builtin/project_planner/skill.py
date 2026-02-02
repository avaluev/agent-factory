"""Project Planner Skill - Transforms ideas into implementation plans."""

import json
from datetime import datetime
from typing import Any
from skills.base import Skill, SkillMetadata, SkillResult, SkillStatus


class ProjectPlannerSkill(Skill):
    """Analyzes ideas and creates comprehensive implementation plans."""
    
    def _default_metadata(self) -> SkillMetadata:
        return SkillMetadata(
            name="project_planner",
            version="1.0.0",
            description="Analyzes user ideas and creates comprehensive implementation plans",
            tags=["planning", "architecture", "project-management"],
            inputs={
                "type": "object",
                "properties": {
                    "idea": {
                        "type": "string",
                        "description": "User's project idea or system concept"
                    },
                    "detail_level": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                        "default": "medium"
                    }
                },
                "required": ["idea"]
            },
            outputs={
                "type": "object",
                "properties": {
                    "plan": {"type": "object"},
                    "tasks": {"type": "array"},
                    "dependencies": {"type": "object"}
                }
            }
        )
    
    async def execute(self, inputs: dict[str, Any]) -> SkillResult:
        """Create a project plan from an idea."""
        from tracing.tracer import Tracer
        from tracing.models import SpanType, SpanStatus
        from core.agent import Agent
        from core.models.anthropic_adapter import AnthropicAdapter
        
        tracer = Tracer.instance()
        span = tracer.start_span(
            SpanType.SKILL,
            name="project_planner_execute",
            input_data={"idea": inputs["idea"][:200]}
        )
        
        start_time = datetime.utcnow()
        
        try:
            idea = inputs["idea"]
            detail_level = inputs.get("detail_level", "medium")
            
            # Use Claude directly for planning with high token limit
            from core.models.base import ChatMessage, MessageRole

            adapter = AnthropicAdapter(model="claude-sonnet-4-5-20250929")

            planning_prompt = f"""Analyze this project idea and create a detailed implementation plan.

PROJECT IDEA:
{idea}

Create a comprehensive plan following this structure:
1. Project overview and goals
2. Recommended technology stack
3. High-level architecture approach
4. 15-30 specific implementation tasks with dependencies
5. Success criteria
6. Potential risks and challenges

CRITICAL: You MUST respond with ONLY a valid JSON object. No markdown, no explanations, no code blocks - just pure JSON.

Use this exact structure:
{{
  "overview": "comprehensive project description with goals",
  "tech_stack": ["technology1", "technology2", "..."],
  "architecture": "high-level system design explanation",
  "tasks": [
    {{
      "id": "task_1",
      "title": "short actionable title",
      "description": "detailed description of what needs to be done",
      "dependencies": [],
      "complexity": "low|medium|high",
      "category": "setup|core|feature|testing|deployment"
    }}
  ],
  "success_criteria": ["criterion1", "criterion2"],
  "risks": ["risk1", "risk2"]
}}

Detail level: {detail_level}

Remember: Output ONLY the JSON object, nothing else."""

            # Call model directly with high token limit for complete response
            messages = [
                ChatMessage(role=MessageRole.USER, content=planning_prompt)
            ]

            response = await adapter.chat(
                messages=messages,
                tools=None,
                temperature=0.7,
                max_tokens=8192  # Higher limit to avoid truncation
            )

            plan_response = response.content

            # Try to parse JSON from response
            plan_data = self._extract_json(plan_response)

            if not plan_data:
                # Try markdown fallback parser
                plan_data = self._parse_markdown_plan(plan_response)

            if not plan_data:
                # Save the full response for debugging
                import os
                debug_path = os.path.expanduser("~/career-automation-project/debug_plan_response.txt")
                with open(debug_path, "w") as f:
                    f.write(plan_response)
                raise ValueError(f"Failed to generate valid plan structure. Full response saved to {debug_path}")
            
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            
            result = SkillResult(
                status=SkillStatus.SUCCESS,
                output={
                    "plan": plan_data,
                    "tasks": plan_data.get("tasks", []),
                    "task_count": len(plan_data.get("tasks", [])),
                    "created_at": datetime.utcnow().isoformat()
                },
                execution_time=execution_time
            )
            
            tracer.end_span(span, status=SpanStatus.SUCCESS, output_data={
                "task_count": len(plan_data.get("tasks", [])),
                "execution_time": execution_time
            })
            
            return result
            
        except Exception as e:
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            tracer.end_span(span, status=SpanStatus.ERROR, error=str(e))
            
            return SkillResult(
                status=SkillStatus.FAILURE,
                output=None,
                error=str(e),
                execution_time=execution_time
            )
    
    def _parse_markdown_plan(self, text: str) -> dict | None:
        """Parse a markdown-formatted plan into JSON structure."""
        import re

        try:
            plan = {
                "overview": "",
                "tech_stack": [],
                "architecture": "",
                "tasks": [],
                "success_criteria": [],
                "risks": []
            }

            # Extract overview (first substantial paragraph or section)
            overview_match = re.search(r'(?:PROJECT OVERVIEW|OVERVIEW)(.*?)(?:TECHNOLOGY STACK|###|\n\n\*\*|$)', text, re.DOTALL | re.IGNORECASE)
            if overview_match:
                plan["overview"] = overview_match.group(1).strip()[:500]

            # Extract tech stack
            tech_match = re.search(r'(?:TECHNOLOGY STACK|TECH STACK)(.*?)(?:ARCHITECTURE|###|$)', text, re.DOTALL | re.IGNORECASE)
            if tech_match:
                tech_text = tech_match.group(1)
                # Extract items from bullet points or lines starting with -
                plan["tech_stack"] = [line.strip('- *').strip() for line in tech_text.split('\n') if line.strip().startswith(('-', '*', '•'))][:20]

            # Extract architecture description
            arch_match = re.search(r'(?:ARCHITECTURE|High-Level System Design)(.*?)(?:TASK BREAKDOWN|###|$)', text, re.DOTALL | re.IGNORECASE)
            if arch_match:
                plan["architecture"] = arch_match.group(1).strip()[:500]

            # Extract tasks - look for **task_N: Title** pattern
            task_pattern = r'\*\*task_(\d+):\s*([^*]+)\*\*\s*\n-\s*Description:\s*([^\n]+)(?:\n-\s*Dependencies:\s*\[([^\]]*)\])?(?:\n-\s*Complexity:\s*(\w+))?(?:\n-\s*Category:\s*(\w+))?'
            for match in re.finditer(task_pattern, text, re.IGNORECASE):
                task_num, title, description, deps, complexity, category = match.groups()
                task = {
                    "id": f"task_{task_num}",
                    "title": title.strip(),
                    "description": description.strip(),
                    "dependencies": [d.strip() for d in (deps or "").split(",")] if deps else [],
                    "complexity": (complexity or "medium").lower(),
                    "category": (category or "core").lower()
                }
                plan["tasks"].append(task)

            # If we found at least some tasks, return the plan
            if len(plan["tasks"]) > 0:
                return plan

            return None

        except Exception as e:
            return None

    def _complete_incomplete_json(self, json_str: str) -> dict | None:
        """Try to complete incomplete JSON by adding missing closing structures."""
        import json

        # Count opening and closing braces/brackets
        open_braces = json_str.count('{')
        close_braces = json_str.count('}')
        open_brackets = json_str.count('[')
        close_brackets = json_str.count(']')

        # Add missing closing structures
        attempts = []

        # Try adding just the missing braces
        attempt1 = json_str
        if attempt1.strip() and not attempt1.strip().endswith(('"', ',', '}', ']')):
            # Ends mid-value, close the string first
            attempt1 += '"'
        attempt1 += '\n' + '}' * (open_braces - close_braces)
        attempt1 += ']' * (open_brackets - close_brackets)
        attempts.append(attempt1)

        # Try adding just task array closure and main object closure
        attempt2 = json_str
        if '"description"' in attempt2 and not attempt2.strip().endswith(('"', '}')):
            # Mid-description, close it
            attempt2 += '"'
        attempt2 += '\n    }\n  ],\n  "success_criteria": [],\n  "risks": []\n}'
        attempts.append(attempt2)

        # Try each attempt
        for attempt in attempts:
            try:
                return json.loads(attempt)
            except json.JSONDecodeError:
                continue

        return None

    def _extract_json(self, text: str) -> dict | None:
        """Extract JSON from text response."""
        import re

        # Try to find JSON in complete code blocks (```json ... ```)
        json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
        if json_match:
            try:
                json_str = json_match.group(1).strip()
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass

        # Try incomplete code block (```json ... without closing)
        json_match = re.search(r'```(?:json)?\s*\n?(.*)', text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1).strip()
            try:
                # Try to parse as-is
                return json.loads(json_str)
            except json.JSONDecodeError:
                # Try to complete incomplete JSON
                completed = self._complete_incomplete_json(json_str)
                if completed:
                    return completed

                # Try to find just the JSON object within it
                inner_match = re.search(r'\{.*\}', json_str, re.DOTALL)
                if inner_match:
                    try:
                        return json.loads(inner_match.group(0))
                    except json.JSONDecodeError:
                        # Try completing this too
                        completed = self._complete_incomplete_json(inner_match.group(0))
                        if completed:
                            return completed

        # Try to find raw JSON (greedy match for nested objects)
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

        return None
