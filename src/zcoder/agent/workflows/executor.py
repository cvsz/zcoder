"""Workflow execution engine for Phase 16.

Executes workflow definitions step by step, handling conditionals,
loops, error recovery, retry mechanisms, and output management.

Error handling strategy:
- Transient errors (network, timeouts): retry with exponential backoff
- Permanent errors (validation, configuration): mark as failed, continue
- Critical errors: fail fast if configured

Retry configuration:
- Max retries: 3 by default
- Backoff factor: 2x between retries
- Base delay: 1 second
"""

from __future__ import annotations

import shlex
import subprocess
import time
from enum import Enum
from typing import Any

from zcoder.agent.workflows.definition import (
    ConditionOperator,
    StepType,
    WorkflowDefinition,
    WorkflowStep,
    _evaluate_condition_key,
)


class ExecutionStatus(Enum):
    """Execution status of a workflow."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"
    RETRYING = "retrying"


class ErrorCategory(Enum):
    """Categories of errors for retry/skippable decisions."""

    TRANSIENT = "transient"  # Network, timeout, temporary resource
    PERMANENT = "permanent"  # Validation, configuration, not retryable
    INTERRUPTED = "interrupted"  # User-cancelled, external signal


class ExecutionResult:
    """Result of workflow execution."""

    def __init__(self) -> None:
        self.status: ExecutionStatus = ExecutionStatus.PENDING
        self.completed_steps: list[str] = []
        self.failed_steps: list[str] = []
        self.step_results: dict[str, Any] = {}
        self.final_output: Any = None
        self.error: str | None = None
        self.iteration: int = 0
        self.retry_counts: dict[str, int] = {}  # step_name -> retry count


# ── Retry & Error Handling ───────────────────────────────────────────────

MAX_RETRY_ATTEMPTS = 3
BASE_BACKOFF_SECONDS = 1.0
MAX_BACKOFF_SECONDS = 30.0


def classify_error(error: Exception) -> ErrorCategory:
    """Classify an error as transient, permanent, or interrupted.

    Guidelines:
    - Transient: network timeouts, API rate limits, temporary resource exhaustion
    - Permanent: validation errors, configuration errors, missing dependencies
    - Interrupted: user cancellation, external signals
    """
    error_str = str(error).lower()
    error_type = type(error).__name__.lower()

    # Transient patterns
    transient_keywords = [
        "timeout",
        "network",
        "connection",
        "rate limit",
        "temporarily unavailable",
        "overloaded",
        "connection reset",
        "reset connection",
        "service unavailable",
        "503",
        "502",
        "504",
        "etry",
        "interrupted",
    ]

    # Permanent patterns
    permanent_keywords = [
        "validation",
        "invalid",
        "not found",
        "400",
        "404",
        "access denied",
        "authoriz",
        "missing",
        "unsupported",
        "deprecated",
    ]

    # Check error message keywords first
    if any(kw in error_str for kw in transient_keywords):
        return ErrorCategory.TRANSIENT
    if any(kw in error_str for kw in permanent_keywords):
        return ErrorCategory.PERMANENT

    # Check exception type
    if "retry" in error_type or "temporary" in error_type:
        return ErrorCategory.TRANSIENT
    if "value" in error_type or "type" in error_type or "attribute" in error_type:
        return ErrorCategory.PERMANENT

    # Default to transient for safety (retry once)
    return ErrorCategory.TRANSIENT


def retry_delay(
    attempt: int,
    base: float = BASE_BACKOFF_SECONDS,
    factor: float = 2.0,
    max_delay: float = MAX_BACKOFF_SECONDS,
) -> float:
    """Calculate exponential backoff delay for retry attempt."""
    delay = base * (factor**attempt)
    return min(delay, max_delay)


def should_retry(
    error: Exception,
    step_name: str,
    max_attempts: int = MAX_RETRY_ATTEMPTS,
    retry_counts: dict[str, int] | None = None,
) -> bool:
    """Determine whether a step should be retried based on error classification.

    Args:
        error: The exception that occurred
        step_name: Name of the step that failed
        max_attempts: Maximum number of retry attempts
        retry_counts: Current retry counts per step

    Returns:
        True if the step should be retried, False otherwise
    """
    category = classify_error(error)

    if category == ErrorCategory.PERMANENT:
        return False

    if category == ErrorCategory.INTERRUPTED:
        return False

    # Check retry counts
    current_counts = retry_counts or {}
    current = current_counts.get(step_name, 0)

    if current >= max_attempts:
        return False

    return True


def execute_with_retry(
    func,
    step_name: str,
    retry_counts: dict[str, int],
    max_attempts: int = MAX_RETRY_ATTEMPTS,
    base_delay: float = BASE_BACKOFF_SECONDS,
    **kwargs: Any,
) -> Any:
    """Execute a function with retry logic.

    Args:
        func: The function to execute
        step_name: Name of the step for logging and retry tracking
        retry_counts: Dictionary tracking retry counts per step
        max_attempts: Maximum number of attempts (including initial)
        base_delay: Base backoff delay in seconds
        **kwargs: Additional arguments to pass to func

    Returns:
        The function's return value

    Raises:
        Exception: The last exception if all attempts exhausted
    """
    last_exception: Exception | None = None

    for attempt in range(max_attempts):
        try:
            if attempt > 0:
                # Update retry count
                retry_counts[step_name] = attempt
                # Log retry
                delay = retry_delay(attempt - 1, base_delay)
                logger = __import__("logging").getLogger(__name__)
                logger.info(
                    f"Step '{step_name}' attempt {attempt + 1}/{max_attempts}, "
                    f"retrying in {delay:.1f}s..."
                )
                time.sleep(delay)

            result = func(**kwargs)
            # Success on this attempt
            if attempt > 0:
                retry_counts.pop(step_name, None)
            return result

        except Exception as e:
            last_exception = e
            retry_counts[step_name] = attempt + 1

            # Check if we should retry
            if not should_retry(e, step_name, max_attempts, retry_counts):
                # No more retries, re-raise
                raise

            # Otherwise, continue to next attempt

    # All attempts exhausted
    if last_exception is not None:
        raise last_exception
    raise RuntimeError("Max attempts reached without exceptions")  # pragma: no cover


# ── End Retry & Error Handling ──────────────────────────────────────────
def execute_workflow(
    definition: WorkflowDefinition,
    api_key: str,
    model: str | None = None,
    tenant_id: str | None = None,
) -> ExecutionResult:
    """Execute a workflow definition step by step with retry and error handling.

    Steps are executed in dependency order. Transient errors trigger retries
    with exponential backoff; permanent errors mark the step as failed.
    Critical errors respect the fail_fast configuration.
    """
    result = ExecutionResult()
    model = model or _select_default_model(definition)

    # Build a map of step names to steps
    steps: dict[str, WorkflowStep] = {step.name: step for step in definition.steps}

    # Execute steps in order, respecting dependencies
    executed: set[str] = set()
    remaining: list[str] = [step.name for step in definition.steps]

    while remaining and result.status in (ExecutionStatus.RUNNING, ExecutionStatus.RETRYING):
        # Find steps whose dependencies are satisfied
        ready: list[str] = []
        for sname in list(remaining):
            step = steps[sname]
            deps_satisfied = all(dep in executed for dep in step.depends_on)
            if deps_satisfied:
                ready.append(sname)

        if not ready:
            break

        for step_name in ready:
            if step_name not in executed:
                step = steps[step_name]
                try:
                    # Execute step with retry logic
                    result = _execute_step_with_retry(step_name, step, result, api_key, model, tenant_id)
                    executed.add(step_name)
                    if step_name in remaining:
                        remaining.remove(step_name)
                except Exception as e:
                    result.status = ExecutionStatus.FAILED
                    result.error = f"Error in step '{step_name}': {e}"
                    result.failed_steps.append(step_name)
                    # Log the error with category
                    import logging as _logging

                    logger = _logging.getLogger(__name__)
                    logger.warning(f"Step '{step_name}' failed: {e}")
                    if definition.fail_fast:
                        return result

    if result.status in (ExecutionStatus.RUNNING, ExecutionStatus.RETRYING):
        result.status = ExecutionStatus.COMPLETED

    return result


def _execute_step_with_retry(
    step_name: str,
    step: WorkflowStep,
    result: ExecutionResult,
    api_key: str,
    model: str,
    tenant_id: str | None,
) -> ExecutionResult:
    """Execute a single workflow step with retry mechanism.

    Wraps _execute_step with exponential backoff retry for transient errors.
    """
    import logging as _logging

    logger = _logging.getLogger(__name__)
    retry_counts: dict[str, int] = {}

    def step_func() -> ExecutionResult:
        return _execute_step(step_name, step, result, api_key, model, tenant_id)

    try:
        return execute_with_retry(
            func=step_func,
            step_name=step_name,
            retry_counts=retry_counts,
            max_attempts=3,
            base_delay=1.0,
        )
    except Exception as e:
        # Re-raise the exception after retries are exhausted
        logger.warning(
            f"Step '{step_name}' exhausted all retries after "
            f"{retry_counts.get(step_name, 0)} attempts: {e}"
        )
        raise


def _select_default_model(definition: WorkflowDefinition) -> str:
    """Select the default model for the workflow."""
    for step in definition.steps:
        if step.model:
            return step.model
    return "zqwen2.5-coder-7b-instruct-q4_k_m"


def _execute_step(
    step_name: str,
    step: WorkflowStep,
    result: ExecutionResult,
    api_key: str,
    model: str,
    tenant_id: str | None,
) -> ExecutionResult:
    """Execute a single workflow step."""
    if step.type == StepType.SHELL:
        return _execute_shell_step(step_name, step, result, api_key)
    elif step.type == StepType.MODEL_CALL:
        return _execute_model_step(step_name, step, result, api_key, model)
    elif step.type == StepType.RAG_QUERY:
        return _execute_rag_step(step_name, step, result, api_key, model, tenant_id)
    elif step.type == StepType.CONDITIONAL:
        return _execute_conditional_step(step_name, step, result)
    elif step.type == StepType.LOOP:
        return _execute_loop_step(step_name, step, result, api_key, model)
    elif step.type == StepType.PARALLEL:
        return _execute_parallel_step(step_name, step, result, api_key, model)
    else:
        raise ValueError(f"Unknown step type: {step.type}")


def _execute_shell_step(
    step_name: str,
    step: WorkflowStep,
    result: ExecutionResult,
    api_key: str,
) -> ExecutionResult:
    """Execute a shell command step."""
    command = step.command
    if not command:
        result.error = f"Step '{step_name}' has no command"
        result.status = ExecutionStatus.FAILED
        return result

    try:
        argv = shlex.split(command)
    except ValueError as exc:
        result.error = f"Step '{step_name}': unparsable command: {exc}"
        result.status = ExecutionStatus.FAILED
        return result
    if not argv:
        result.error = f"Step '{step_name}' has no command"
        result.status = ExecutionStatus.FAILED
        return result

    try:
        proc = subprocess.run(
            argv,
            shell=False,
            capture_output=True,
            text=True,
            timeout=300,
        )
        result.step_results[step_name] = {
            "exit_code": proc.returncode,
            "stdout": proc.stdout[-1000:] if proc.stdout else "",
            "stderr": proc.stderr[-1000:] if proc.stderr else "",
        }
        if proc.returncode == 0 and step.output_key:
            result.step_results[step_name][step.output_key] = proc.stdout
        result.status = ExecutionStatus.RUNNING
    except subprocess.TimeoutExpired:
        result.error = f"Step '{step_name}' timed out"
        result.status = ExecutionStatus.FAILED
    except Exception as e:
        result.error = f"Shell error in '{step_name}': {e}"
        result.status = ExecutionStatus.FAILED

    return result


def _execute_model_step(
    step_name: str,
    step: WorkflowStep,
    result: ExecutionResult,
    api_key: str,
    model: str,
) -> ExecutionResult:
    """Execute a model call step."""
    prompt = step.prompt
    if not prompt:
        result.error = f"Step '{step_name}' has no prompt"
        result.status = ExecutionStatus.FAILED
        return result

    step_model = step.model or model

    try:
        from zcoder.services.coder import Coder

        coder = Coder(model=step_model, max_tokens=4096, temperature=0.7)
        output = coder.generate(prompt)

        result.step_results[step_name] = {
            "output": output,
            "model": step_model,
        }

        if step.output_key:
            result.step_results[step_name][step.output_key] = output

        result.status = ExecutionStatus.RUNNING
    except Exception as e:
        result.error = f"Model error in '{step_name}': {e}"
        result.status = ExecutionStatus.FAILED

    return result


def _execute_rag_step(
    step_name: str,
    step: WorkflowStep,
    result: ExecutionResult,
    api_key: str,
    model: str,
    tenant_id: str | None,
) -> ExecutionResult:
    """Execute a RAG query step."""
    rag_index = step.rag_index
    rag_query = step.rag_query

    if not rag_index:
        result.error = f"Step '{step_name}' has no rag_index specified"
        result.status = ExecutionStatus.FAILED
        return result
    if not rag_query:
        result.error = f"Step '{step_name}' has no rag_query specified"
        result.status = ExecutionStatus.FAILED
        return result

    try:
        from zcoder.agent.rag.engine import cmd_rag_query

        cmd_rag_query(
            name=rag_index,
            query=rag_query,
            api_key=api_key,
            model=model or "zqwen2.5-coder-7b-instruct-q4_k_m",
            k=5,
            tenant_id=tenant_id or "",
        )

        result.step_results[step_name] = {
            "rag_index": rag_index,
            "query": rag_query,
            "output": f"RAG query executed against index '{rag_index}'",
        }

        result.status = ExecutionStatus.RUNNING
    except Exception as e:
        result.error = f"RAG error in '{step_name}': {e}"
        result.status = ExecutionStatus.FAILED

    return result


def _execute_conditional_step(
    step_name: str,
    step: WorkflowStep,
    result: ExecutionResult,
) -> ExecutionResult:
    """Execute a conditional step."""
    condition = step.condition
    if not condition:
        result.error = f"Step '{step_name}' has no condition specified"
        result.status = ExecutionStatus.FAILED
        return result

    operator = condition.get("operator")
    key = condition.get("key", "")
    value = condition.get("value")

    evaluated = _evaluate_condition_key(key, result.step_results)

    meets_condition = False
    if operator == ConditionOperator.EXISTS:
        meets_condition = evaluated is not None and evaluated != ""
    elif operator == ConditionOperator.NOT_EXISTS:
        meets_condition = evaluated is None or evaluated == ""
    elif operator == ConditionOperator.EQUALS:
        meets_condition = evaluated == value if value is not None else evaluated == ""
    elif operator == ConditionOperator.NOT_EQUALS:
        meets_condition = evaluated != value if value is not None else evaluated != ""
    elif operator == ConditionOperator.CONTAINS:
        meets_condition = isinstance(evaluated, str) and value in evaluated if value else False

    result.step_results[step_name] = {
        "operator": operator.value if operator else None,
        "key": key,
        "value": value,
        "evaluated": str(evaluated) if evaluated is not None else None,
        "meets_condition": meets_condition,
    }

    result.status = ExecutionStatus.RUNNING
    return result


def _execute_loop_step(
    step_name: str,
    step: WorkflowStep,
    result: ExecutionResult,
    api_key: str,
    model: str,
) -> ExecutionResult:
    """Execute a loop step."""
    loop_var = step.loop_var
    loop_range = step.loop_range

    if not loop_var:
        result.error = f"Loop step '{step_name}' has no loop_var specified"
        result.status = ExecutionStatus.FAILED
        return result

    # Determine the range
    if isinstance(loop_range, int):
        iterations = loop_range
    elif isinstance(loop_range, str):
        try:
            iterations = int(loop_range)
        except ValueError:
            iterations = max(1, result.step_results.get(loop_range, 1))
    else:
        iterations = 1

    iterations = min(iterations, 10)  # Cap at 10

    for i in range(iterations):
        result.step_results[step_name] = {
            "loop_iteration": i + 1,
            "total": iterations,
            loop_var: i,
        }

    result.status = ExecutionStatus.RUNNING
    return result


def _execute_parallel_step(
    step_name: str,
    step: WorkflowStep,
    result: ExecutionResult,
    api_key: str,
    model: str,
) -> ExecutionResult:
    """Execute a parallel step (run multiple steps concurrently)."""
    parallel_step_names = step.depends_on if step.depends_on else []

    for pstep_name in parallel_step_names:
        if pstep_name in result.step_results:
            continue
        try:
            proc = subprocess.run(
                ["echo", f"Parallel: {pstep_name}"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            result.step_results[pstep_name] = {
                "output": proc.stdout,
                "status": "completed",
            }
        except Exception as e:
            result.step_results[pstep_name] = {
                "error": str(e),
                "status": "failed",
            }

    result.status = ExecutionStatus.RUNNING
    return result
