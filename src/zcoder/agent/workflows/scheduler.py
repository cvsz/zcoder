"""Workflow scheduling and trigger configuration for Phase 16/17.

Provides declarative workflow scheduling with time-based triggers,
event-based triggers, and cron-style scheduling patterns.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any


class TriggerType(Enum):
    """Types of workflow triggers."""

    NONE = "none"
    CRON = "cron"
    INTERVAL = "interval"
    WEBHOOK = "webhook"
    EVENT = "event"


@dataclass
class Trigger:
    """Represents a workflow trigger configuration."""

    type: TriggerType
    # Cron schedule (for CRON type)
    schedule: str = ""  # e.g., "0 2 * * *" (daily at 2 AM)
    # Interval in minutes (for INTERVAL type)
    interval_minutes: int = 0
    # Webhook URL (for WEBHOOK type)
    webhook_url: str = ""
    # Event name (for EVENT type)
    event_name: str = ""
    # Condition that must be met
    condition: dict[str, Any] | None = None


@dataclass
class WorkflowSchedule:
    """Complete workflow schedule configuration."""

    name: str
    description: str = ""
    trigger: Trigger = field(default_factory=lambda: Trigger(type=TriggerType.NONE))
    max_runs: int = -1  # -1 = unlimited
    concurrent_runs: bool = False  # Allow concurrent executions
    timeout_minutes: int = 60


def load_workflow_schedule(filepath: str | Path) -> WorkflowSchedule:
    """
    Load a workflow schedule from a JSON file.

    Expected JSON format:
    ```json
    {
      "name": "daily-indexing",
      "description": "Index new documents daily",
      "trigger": {
        "type": "cron",
        "schedule": "0 3 * * *"
      },
      "max_runs": -1,
      "concurrent_runs": false,
      "timeout_minutes": 120
    }
    """
    import json

    with open(filepath) as f:
        data = json.load(f)

    trigger_data = data.get("trigger", {})
    trigger_type = TriggerType(trigger_data.get("type", "none"))

    trigger = Trigger(
        type=trigger_type,
        schedule=trigger_data.get("schedule", ""),
        interval_minutes=trigger_data.get("interval_minutes", 0),
        webhook_url=trigger_data.get("webhook_url", ""),
        event_name=trigger_data.get("event_name", ""),
        condition=trigger_data.get("condition"),
    )

    return WorkflowSchedule(
        name=data.get("name", "unnamed-schedule"),
        description=data.get("description", ""),
        trigger=trigger,
        max_runs=data.get("max_runs", -1),
        concurrent_runs=data.get("concurrent_runs", False),
        timeout_minutes=data.get("timeout_minutes", 60),
    )


def save_workflow_schedule(schedule: WorkflowSchedule, filepath: str | Path) -> None:
    """
    Save a workflow schedule to a JSON file.
    """
    import json

    data: dict[str, Any] = {
        "name": schedule.name,
        "description": schedule.description,
        "trigger": {
            "type": schedule.trigger.type.value,
            "schedule": schedule.trigger.schedule,
            "interval_minutes": schedule.trigger.interval_minutes,
            "webhook_url": schedule.trigger.webhook_url,
            "event_name": schedule.trigger.event_name,
            "condition": schedule.trigger.condition,
        },
        "max_runs": schedule.max_runs,
        "concurrent_runs": schedule.concurrent_runs,
        "timeout_minutes": schedule.timeout_minutes,
    }

    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)


def evaluate_trigger_conditions(
    trigger: Trigger,
    event_data: dict[str, Any] | None = None,
) -> bool:
    """
    Evaluate whether a trigger should fire based on event data and conditions.

    Args:
        trigger: The trigger configuration to evaluate
        event_data: Optional event data (for EVENT type triggers)

    Returns:
        True if the trigger should fire, False otherwise
    """
    # Check if conditions are met
    if trigger.condition:
        if not _check_condition(trigger.condition, event_data or {}):
            return False

    # Type-specific checks
    if trigger.type == TriggerType.CRON:
        # Check current time against cron schedule
        if trigger.schedule:
            return _check_cron_schedule(trigger.schedule)
        return False

    if trigger.type == TriggerType.INTERVAL:
        # Check if enough time has passed since last run
        # In a real implementation, track last run time in workflow state
        # For now, return True if no specific last-run tracking is available
        return True

    if trigger.type == TriggerType.EVENT:
        if not event_data:
            return False
        # Check event-specific conditions
        return True

    if trigger.type == TriggerType.WEBHOOK:
        if not trigger.webhook_url:
            return False
        return True

    # No trigger type = no scheduling
    return False


def _check_condition(
    condition: dict[str, Any],
    data: dict[str, Any],
) -> bool:
    """Check a condition against data dictionary."""
    operator = condition.get("operator")
    key = condition.get("key", "")
    value = condition.get("value")

    # Evaluate path in data
    parts = key.split(".", 1)
    current = data
    for k in parts:
        if isinstance(current, dict) and k in current:
            current = current[k]
        else:
            return False

    if operator == "exists":
        return current is not None and current != ""
    elif operator == "not_exists":
        return current is None or current == ""
    elif operator == "equals":
        return current == value if value is not None else current == ""
    elif operator == "not_equals":
        return current != value if value is not None else current != ""
    elif operator == "contains":
        return isinstance(current, str) and (value in current if value else False)
    elif operator == "not_contains":
        return not (isinstance(current, str) and (value in current if value else False))
    elif operator == "greater_than":
        return float(current) > float(value) if isinstance(current, (int, float)) else False
    elif operator == "less_than":
        return float(current) < float(value) if isinstance(current, (int, float)) else False
    else:
        return False


def _check_cron_schedule(cron_schedule: str) -> bool:
    """Check if the current time matches a cron schedule pattern.

    Supports standard cron format: minute hour day month weekday
    e.g., "0 3 * * *" = daily at 3 AM
    Also supports simplified forms: "*/5 * * * *" = every 5 minutes

    Returns True if the current time matches the schedule.
    """
    try:
        # Parse cron schedule
        parts = cron_schedule.strip().split()
        if len(parts) != 5:
            # simplified format or invalid
            return False

        minute, hour, day_of_month, month, day_of_week = parts

        now = datetime.now(UTC)
        now_minute = now.minute
        now_hour = now.hour
        now_day = now.day
        now_month = now.month
        now_weekday = now.weekday()  # 0=Monday, 6=Sunday

        # Match minute
        if minute.startswith("*/"):
            # Every N minutes
            interval = int(minute[2:])
            if now_minute % interval != 0:
                return False
        elif minute != "*":
            # Specific minute
            if int(minute) != now_minute:
                return False

        # Match hour
        if hour.startswith("*/"):
            # Every N hours (not standard cron, but supported)
            interval = int(hour[2:])
            if now_hour % interval != 0:
                return False
        elif hour != "*":
            # Specific hour
            if int(hour) != now_hour:
                return False

        # Match month
        if month != "*":
            if int(month) != now_month:
                return False

        # Match day - handle both day-of-month and day-of-week
        # Standard cron: if both day-of-month and day-of-week are specified (not *),
        # match if either matches (OR logic)
        dom_specified = day_of_month != "*"
        dow_specified = day_of_week != "*"

        if dom_specified and dow_specified:
            # Both specified: match if either matches
            dom_match = _match_day_of_month(day_of_month, now_day)
            dow_match = _match_day_of_week(day_of_week, now_weekday)
            if not (dom_match or dow_match):
                return False
        elif dom_specified:
            # Only day-of-month specified
            if not _match_day_of_month(day_of_month, now_day):
                return False
        elif dow_specified:
            # Only day-of-week specified
            if not _match_day_of_week(day_of_week, now_weekday):
                return False
        # If neither specified (* *), always match

        return True

    except (ValueError, IndexError):
        # Invalid cron schedule - don't fire
        return False


def _match_day_of_month(pattern: str, current_day: int) -> bool:
    """Check if current day matches a day-of-month pattern."""
    if pattern == "*":
        return True
    # Handle ranges and steps
    # Simple exact match first
    try:
        if "/" in pattern:
            base, step = pattern.split("/")
            step_n = int(step)
            base_matches = base == "*" or int(base) == current_day
            if base_matches and current_day % step_n != 0:
                return False
            return base_matches
        else:
            return int(pattern) == current_day
    except ValueError:
        return False


def _match_day_of_week(pattern: str, current_weekday: int) -> bool:
    """Check if current weekday matches a day-of-week pattern.

    Cron weekday: 0=Sunday, 1=Monday, ..., 6=Saturday
    Python weekday: 0=Monday, 1=Tuesday, ..., 6=Sunday
    """
    # Convert Python weekday (0=Mon) to cron weekday (0=Sun)
    cron_weekday = (current_weekday + 1) % 7

    if pattern == "*":
        return True

    try:
        # Handle steps
        if "/" in pattern:
            base, step = pattern.split("/")
            step_n = int(step)
            base_matches = _cron_weekday_matches(base, cron_weekday)
            if base_matches and cron_weekday % step_n != 0:
                return False
            return base_matches
        else:
            return _cron_weekday_matches(pattern, cron_weekday)
    except ValueError:
        return False


def _cron_weekday_matches(pattern: str, cron_weekday: int) -> bool:
    """Check if a cron weekday pattern matches the current weekday."""
    if pattern == "*":
        return True
    # Handle list of days (e.g., "1,3" for Mon,Wed)
    if "," in pattern:
        days = [int(d.strip()) for d in pattern.split(",")]
        return cron_weekday in days
    # Single day
    day_num = int(pattern)
    return cron_weekday == day_num


# Global registry for scheduled workflows
_scheduled_workflows: dict[str, WorkflowSchedule] = {}


def register_schedule(name: str, schedule: WorkflowSchedule) -> None:
    """Register a workflow schedule in the global registry."""
    _scheduled_workflows[name] = schedule


def get_schedule(name: str) -> WorkflowSchedule | None:
    """Get a scheduled workflow by name."""
    return _scheduled_workflows.get(name)


def list_schedules() -> list[str]:
    """List all registered workflow schedule names."""
    return list(_scheduled_workflows.keys())


def trigger_workflow(
    schedule_name: str,
    event_data: dict[str, Any] | None = None,
) -> bool:
    """
    Attempt to trigger a scheduled workflow.

    Returns True if the trigger conditions are met and workflow should run.
    """
    schedule = get_schedule(schedule_name)
    if not schedule:
        return False

    return evaluate_trigger_conditions(schedule.trigger, event_data)
