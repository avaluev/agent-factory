---
name: project_planner
version: 1.0.0
description: Analyzes user ideas and creates comprehensive implementation plans with task breakdowns
author: Agent Factory
tags: [planning, architecture, project-management]
inputs:
  type: object
  properties:
    idea:
      type: string
      description: User's project idea or system concept
    detail_level:
      type: string
      enum: [high, medium, low]
      default: medium
      description: Level of detail in the plan
  required: [idea]
outputs:
  type: object
  properties:
    plan:
      type: object
      description: Comprehensive project plan
    tasks:
      type: array
      description: List of implementation tasks
    dependencies:
      type: object
      description: Task dependency graph
---

# Project Planner Skill

Transforms user ideas into actionable implementation plans.

## Capabilities

- Requirements analysis
- Task decomposition (10-50 tasks)
- Dependency mapping
- Success criteria definition
- Technology stack recommendation
- Risk identification

## Example

Input: "Build a REST API for a blog platform"

Output:
- 25 implementation tasks
- Database schema design
- API endpoint definitions
- Authentication flow
- Testing strategy
- Deployment checklist
