"""Workflow definition module for Phase 16.

Provides declarative YAML-based workflow definition format with
step orchestration, conditional branching, looping, and scheduling.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

from zcoder.agent.workflows.scheduler import (
    Trigger,
    TriggerType,
    WorkflowSchedule,
)


class StepType(Enum):
    """Types of workflow steps."""

    SHELL = "shell"
    MODEL_CALL = "model_call"
    RAG_QUERY = "rag_query"
    CONDITIONAL = "conditional"
    LOOP = "loop"
    PARALLEL = "parallel"


class ConditionOperator(Enum):
    """Operators for conditional steps."""

    EXISTS = "exists"
    NOT_EXISTS = "not_exists"
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"
    CONTAINS = "contains"


@dataclass
class WorkflowStep:
    """Represents a single step in a workflow."""

    name: str
    type: StepType
    # Step-specific fields
    prompt: str | None = None
    model: str | None = None
    rag_index: str | None = None
    rag_query: str | None = None
    command: str | None = None
    # Conditional/loop fields
    condition: dict[str, Any] | None = None
    loop_var: str | None = None
    loop_range: int | str | None = None
    # Output fields
    output_path: str | None = None
    output_key: str | None = None
    # Dependencies
    depends_on: list[str] = field(default_factory=list)


@dataclass
class WorkflowDefinition:
    """Complete workflow definition."""

    name: str
    description: str = ""
    steps: list[WorkflowStep] = field(default_factory=list)
    variables: dict[str, Any] = field(default_factory=dict)
    # Global settings
    max_iterations: int = 10
    timeout_minutes: int = 60
    fail_fast: bool = True
    # Scheduling
    schedule: WorkflowSchedule | None = field(default=None)


def load_workflow_yaml(filepath: str | Path) -> WorkflowDefinition:
    """
    Load a workflow definition from a YAML file.

    Expected YAML format:
    ```yaml
    name: my-workflow
    description: Process documents with AI

    variables:
      input_dir: ./docs
      output_dir: ./results

    schedule:
      type: cron
      schedule: "0 3 * * *"  # Daily at 3 AM

    variables:
      input_dir: ./docs
      output_dir: ./results

    steps:
      - name: index-docs
        type: shell
        command: |
          zcoder --rag-index index1 ${{variables.input_dir}} --rag-tenant tenant1

      - name: analyze-with-model
        type: model_call
        model: claude-sonnet-5-5
        prompt: |
          Analyze the following content and summarize key findings:
          {{step.index-docs.result}}

      - name: conditional-branch
        type: conditional
        condition:
          operator: exists
          key: step.analyze-with-model.result
          value: ""

      - name: branch-yes
        type: shell
        condition: true
        command: echo "Analysis complete"

      - name: branch-no
        type: shell
        condition: false
        command: echo "No results to analyze"
    """
    with open(filepath) as f:
        data = yaml.safe_load(f)

    if data is None:
        return WorkflowDefinition(name="empty-workflow")

    # Parse schedule
    schedule_data = data.get("schedule")
    schedule: WorkflowSchedule | None = None
    if schedule_data:
        schedule_type = schedule_data.get("type", "none")
        try:
            trigger_type = TriggerType(schedule_type)
        except ValueError:
            trigger_type = TriggerType.NONE

        schedule = WorkflowSchedule(
            name=schedule_data.get("name", ""),
            description=schedule_data.get("description", ""),
            trigger=Trigger(
                type=trigger_type,
                schedule=schedule_data.get("schedule", ""),
                interval_minutes=schedule_data.get("interval_minutes", 0),
                webhook_url=schedule_data.get("webhook_url", ""),
                event_name=schedule_data.get("event_name", ""),
                condition=schedule_data.get("condition"),
            ),
            max_runs=schedule_data.get("max_runs", -1),
            concurrent_runs=schedule_data.get("concurrent_runs", False),
            timeout_minutes=schedule_data.get("timeout_minutes", 60),
        )

    # Parse steps
    steps: list[WorkflowStep] = []
    for step_data in data.get("steps", []):
        step = _parse_step(step_data)
        if step:
            steps.append(step)

    return WorkflowDefinition(
        name=data.get("name", "unnamed-workflow"),
        description=data.get("description", ""),
        steps=steps,
        variables=data.get("variables", {}),
        max_iterations=data.get("max_iterations", 10),
        timeout_minutes=data.get("timeout_minutes", 60),
        fail_fast=data.get("fail_fast", True),
        schedule=schedule,
    )


def _parse_step(step_data: dict[str, Any]) -> WorkflowStep | None:
    """Parse a single step from YAML data."""
    if not step_data or "name" not in step_data:
        return None

    name = step_data["name"]
    step_type = step_data.get("type", "shell")

    try:
        step_type_enum = StepType(step_type)
    except ValueError:
        step_type_enum = StepType.SHELL

    # Extract step-specific fields
    prompt = step_data.get("prompt")
    model = step_data.get("model")
    rag_index = step_data.get("rag_index")
    rag_query = step_data.get("rag_query")
    command = step_data.get("command")

    # Extract conditional/loop fields
    condition = step_data.get("condition")
    loop_var = step_data.get("loop_var")
    loop_range = step_data.get("loop_range")

    # Extract output fields
    output_path = step_data.get("output_path")
    output_key = step_data.get("output_key")

    # Extract dependencies
    depends_on = step_data.get("depends_on", [])

    return WorkflowStep(
        name=name,
        type=step_type_enum,
        prompt=prompt,
        model=model,
        rag_index=rag_index,
        rag_query=rag_query,
        command=command,
        condition=condition,
        loop_var=loop_var,
        loop_range=loop_range,
        output_path=output_path,
        output_key=output_key,
        depends_on=depends_on,
    )


def save_workflow_yaml(definition: WorkflowDefinition, filepath: str | Path) -> None:
    """
    Save a workflow definition to a YAML file.
    """

    # Convert to dict
    def _step_to_dict(step: WorkflowStep) -> dict[str, Any]:
        d: dict[str, Any] = {
            "name": step.name,
            "type": step.type.value,
        }
        if step.prompt:
            d["prompt"] = step.prompt
        if step.model:
            d["model"] = step.model
        if step.rag_index:
            d["rag_index"] = step.rag_index
        if step.rag_query:
            d["rag_query"] = step.rag_query
        if step.command:
            d["command"] = step.command
        if step.condition:
            d["condition"] = step.condition
        if step.loop_var:
            d["loop_var"] = step.loop_var
        if step.loop_range is not None:
            d["loop_range"] = step.loop_range
        if step.output_path:
            d["output_path"] = step.output_path
        if step.output_key:
            d["output_key"] = step.output_key
        if step.depends_on:
            d["depends_on"] = step.depends_on
        return d

    # Add schedule if present
    schedule_data: dict[str, Any] = {}
    if definition.schedule:
        schedule_data = {
            "name": definition.schedule.name,
            "description": definition.schedule.description,
            "type": definition.schedule.trigger.type.value,
            "schedule": definition.schedule.trigger.schedule,
            "interval_minutes": definition.schedule.trigger.interval_minutes,
            "webhook_url": (
                definition.schedule.trigger.webhook_url
                if hasattr(definition.schedule.trigger, "webhook_url")
                else ""
            ),
            "event_name": definition.schedule.trigger.event_name,
            "condition": definition.schedule.trigger.condition,
            "max_runs": definition.schedule.max_runs,
            "concurrent_runs": definition.schedule.concurrent_runs,
            "timeout_minutes": definition.schedule.timeout_minutes,
        }

    data: dict[str, Any] = {
        "name": definition.name,
        "description": definition.description,
        "variables": definition.variables,
        "steps": [_step_to_dict(s) for s in definition.steps],
        "max_iterations": definition.max_iterations,
        "timeout_minutes": definition.timeout_minutes,
        "fail_fast": definition.fail_fast,
    }

    if schedule_data:
        data["schedule"] = schedule_data

    with open(filepath, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def _evaluate_condition_key(key: str, step_results: dict[str, Any]) -> Any:
    """Evaluate a condition key against step results."""
    parts = key.split(".", 1)
    if len(parts) == 2:
        step_name, result_key = parts
        current = step_results
        for k in [step_name, result_key]:
            if isinstance(current, dict) and k in current:
                current = current[k]
            else:
                return None
        return current
    else:
        return step_results.get(parts[0], None)
