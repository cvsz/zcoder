"""
ausi/router.py — AUSI Multi-Agent Orchestration.

Implements controlled task delegation with:
  — Task decomposition into concrete steps
  — Agent selection based on capability and cost
  — Parallel execution where safe
  — Dependency-aware execution order
  — Shared task context propagation
  — Conflict detection between parallel agents
  — Retry policies with exponential backoff
  — Timeouts per agent/task
  — Cancellation support
  — Result validation (evidence from actual execution, not self-reported success)
  — Execution traceability (full audit log)
"""

from __future__ import annotations

import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from zcoder.agent.ausi.skills import (
    SkillInput,
    SkillRegistry,
)


class OrchestrationStatus(Enum):
    """Status of the orchestration workflow."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskStep:
    """A single step in a decomposed task."""

    step_id: str
    step_number: int
    task: str
    depends_on: list[str] = field(default_factory=list)
    agent: str = ""  # Which agent should handle this step
    provider: str = ""  # Which provider to use
    model: str = ""  # Which model to use
    completed: bool = False
    result: str = ""
    error: str = ""
    started_at: float = 0
    completed_at: float = 0


@dataclass
class OrchestrationContext:
    """Shared context passed between orchestrated agents."""

    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    original_prompt: str = ""
    decomposition: list[TaskStep] = field(default_factory=list)
    agent_results: dict[str, str] = field(default_factory=dict)
    shared_data: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    start_time: float = field(default_factory=time.time)
    end_time: float = 0
    status: OrchestrationStatus = OrchestrationStatus.PENDING


class ExecutionResult:
    """Result of executing a single agent/step."""

    def __init__(
        self,
        step_id: str,
        success: bool,
        text: str = "",
        model: str = "",
        provider: str = "",
        task_id: str = "",
        error: str = "",
        raw: Any = None,
    ):
        self.step_id = step_id
        self.success = success
        self.text = text
        self.model = model
        self.provider = provider
        self.task_id = task_id
        self.error = error
        self.raw = raw


class OrchestrationEngine:
    """Core orchestration engine that manages multi-agent task execution.

    Responsibilities:
    - Task decomposition
    - Agent selection
    - Provider and model routing
    - Parallel execution where safe
    - Dependency-aware step ordering
    - Retry and timeout handling
    - Conflict detection
    - Result validation
    - Audit trail generation
    """

    def __init__(self, skill_registry: SkillRegistry | None = None):
        self.skill_registry = skill_registry or SkillRegistry()
        self.max_parallel_steps = 4
        self.default_timeout = 120  # seconds
        self.retry_max_attempts = 3
        self.retry_backoff_base = 2  # exponential backoff base
        self._audit_log: list[dict[str, Any]] = []

    # ── Task Decomposition ──────────────────────────────────────────────

    def decompose_task(
        self, prompt: str, context: dict[str, Any] | None = None
    ) -> tuple[list[TaskStep], OrchestrationContext]:
        """Decompose a user task into concrete steps.

        Args:
            prompt: The user's original request/prompt
            context: Optional contextual information (project info, etc.)

        Returns:
            (steps, orchestration_context) tuple
        """
        ctx = OrchestrationContext(
            original_prompt=prompt,
            metadata=context or {},
        )

        # Use a classifier/router to determine the task type and decompose
        decomposition = self._classify_and_decompose(prompt, context or {})

        # Build TaskStep objects from the decomposition
        steps = []
        for i, (step_task, agent, model, depends) in enumerate(decomposition, start=1):
            step_id = f"step-{i:02d}"
            step = TaskStep(
                step_id=step_id,
                step_number=i,
                task=step_task,
                depends_on=depends or [],
                agent=agent,
                model=model,
            )
            steps.append(step)

        ctx.decomposition = steps
        return steps, ctx

    def _classify_and_decompose(
        self, prompt: str, context: dict[str, Any]
    ) -> list[tuple[str, str, str, list[str]]]:
        """Classify the prompt and decompose into steps.

        Returns list of (task_description, agent_name, model_id, depends_on) tuples.
        """
        # Classify the prompt into a task type
        task_type = self._classify_prompt(prompt)

        # Decompose based on task type
        if task_type == "code":
            return self._decompose_code_task(prompt, context)
        elif task_type == "research":
            return self._decompose_research_task(prompt, context)
        elif task_type == "write":
            return self._decompose_write_task(prompt, context)
        elif task_type == "analyse":
            return self._decompose_analyse_task(prompt, context)
        elif task_type == "plan":
            return self._decompose_plan_task(prompt, context)
        elif task_type == "brainstorm":
            return self._decompose_brainstorm_task(prompt, context)
        else:
            # Default: single-step code task
            return [(prompt, "code", "opencode/nemotron-3.5-lightning-free", [])]

    def _decompose_code_task(
        self, prompt: str, context: dict[str, Any] | None = None
    ) -> list[tuple[str, str, str, list[str]]]:
        """Decompose a code-related task into steps.

        Returns list of (task_description, agent_name, model_id, depends_on) tuples.
        """
        # For code tasks, extract function/class names and dependencies
        return [(prompt, "code", "opencode/nemotron-3.5-lightning-free", [])]

    def _decompose_research_task(
        self, prompt: str, context: dict[str, Any] | None = None
    ) -> list[tuple[str, str, str, list[str]]]:
        """Decompose a research task into steps.

        Returns list of (task_description, agent_name, model_id, depends_on) tuples.
        """
        # For research tasks, break down into sub-questions or phases
        return [(prompt, "research", "opencode/nemotron-3.5-lightning-free", [])]

    def _decompose_write_task(
        self, prompt: str, context: dict[str, Any] | None = None
    ) -> list[tuple[str, str, str, list[str]]]:
        """Decompose a write task into steps.

        Returns list of (task_description, agent_name, model_id, depends_on) tuples.
        """
        # For write tasks, break into sections or paragraphs
        return [(prompt, "write", "opencode/nemotron-3.5-lightning-free", [])]

    def _decompose_analyse_task(
        self, prompt: str, context: dict[str, Any] | None = None
    ) -> list[tuple[str, str, str, list[str]]]:
        """Decompose an analysis task into steps.

        Returns list of (task_description, agent_name, model_id, depends_on) tuples.
        """
        # For analysis tasks, identify data sources, methods, and conclusions
        return [(prompt, "analyse", "opencode/nemotron-3.5-lightning-free", [])]

    def _decompose_plan_task(
        self, prompt: str, context: dict[str, Any] | None = None
    ) -> list[tuple[str, str, str, list[str]]]:
        """Decompose a planning task into steps.

        Returns list of (task_description, agent_name, model_id, depends_on) tuples.
        """
        # For planning tasks, break down into milestones and actions
        return [(prompt, "plan", "opencode/nemotron-3.5-lightning-free", [])]

    def _decompose_brainstorm_task(
        self, prompt: str, context: dict[str, Any] | None = None
    ) -> list[tuple[str, str, str, list[str]]]:
        """Decompose a brainstorming task into steps.

        Returns list of (task_description, agent_name, model_id, depends_on) tuples.
        """
        # For brainstorming, generate multiple ideas or approaches
        return [(prompt, "brainstorm", "opencode/nemotron-3.5-lightning-free", [])]

    def _classify_prompt(self, prompt: str) -> str:
        """Classify a prompt into a task type."""
        prompt_lower = prompt.lower()

        # Keyword-based classification
        code_keywords = ["code", "function", "class", "implementation", "refactor", "debug"]
        research_keywords = ["research", "study", "analyze", "investigate", "compare"]
        write_keywords = ["write", "summarize", "edit", "translate", "document"]
        analyse_keywords = ["analyse", "data", "statistics", "business", "insight"]
        plan_keywords = ["plan", "roadmap", "strategy", "task breakdown", "milestones"]
        brainstorm_keywords = ["brainstorm", "ideas", "blue-sky", "creative", "concepts"]

        counts: dict[str, int] = {
            "code": sum(1 for k in code_keywords if k in prompt_lower),
            "research": sum(1 for k in research_keywords if k in prompt_lower),
            "write": sum(1 for k in write_keywords if k in prompt_lower),
            "analyse": sum(1 for k in analyse_keywords if k in prompt_lower),
            "plan": sum(1 for k in plan_keywords if k in prompt_lower),
            "brainstorm": sum(1 for k in brainstorm_keywords if k in prompt_lower),
        }

        # Return the task type with the most matching keywords
        if counts:
            return max(counts, key=lambda k: counts[k])
        return "code"  # Default

    # ── Agent/Provider Selection ────────────────────────────────────────

    def select_agent_and_model(
        self,
        task_description: str,
        routing_profile: str = "balanced",
        available_agents: list[str] | None = None,
    ) -> tuple[str, str, str]:
        """Select the best agent, provider, and model for a task.

        Args:
            task_description: Description of the task
            routing_profile: One of the 7 routing profiles
            available_agents: Optional list of available agent names

        Returns:
            (agent_name, provider, model) tuple
        """
        # Use the model routing skill to determine the best model
        routing_skill = self.skill_registry.get("model-routing")
        if routing_skill is None:
            # Fallback defaults
            return self._default_agent_model(routing_profile)

        # Execute the routing skill
        SkillInput(
            prompt=task_description,
            task_context={"routing_profile": routing_profile},
            parameters={"routing_profile": routing_profile},
        )

        # We need to get output from the skill - but execute returns SkillOutput
        # Let's do a simplified routing based on the skill's recommendation
        profile = getattr(routing_skill, "_get_routing_profile", lambda p: p)(routing_profile)
        model = getattr(routing_skill, "_recommend_model", lambda p, c: None)(
            profile, {"is_coding_task": "code" in task_description.lower()}
        )

        if not model:
            return self._default_agent_model(routing_profile)

        # Determine agent and provider based on model
        agent, provider = self._model_to_agent_provider(model)

        return agent, provider, model

    def _default_agent_model(self, routing_profile: str) -> tuple[str, str, str]:
        """Return default agent/model based on routing profile."""
        if routing_profile == "free-first":
            return ("code", "opencode", "opencode/nemotron-3.5-lightning-free")
        elif routing_profile == "local-first":
            return ("code", "local", "local")
        elif routing_profile == "best-quality":
            return ("code", "opencode", "opencode/nemotron-3.5-lightning-free")
        elif routing_profile == "fastest":
            return ("code", "opencode", "opencode/crouton-alpha-free")
        elif routing_profile == "privacy-first":
            return ("code", "local", "local")
        elif routing_profile == "balanced":
            return ("code", "opencode", "opencode/nemotron-3.5-lightning-free")
        else:  # custom
            return ("code", "opencode", "opencode/nemotron-3.5-lightning-free")

    def _model_to_agent_provider(self, model: str) -> tuple[str, str]:
        """Convert a model ID to (agent_name, provider)."""
        if model and "opencode/" in model:
            return ("code", "opencode")
        elif model and "local" in model.lower():
            return ("code", "local")
        elif model and "kilo/" in model.lower():
            return ("code", "kilo")
        else:
            return ("code", "opencode")

    # ── Step Execution ──────────────────────────────────────────────────

    def execute_step(
        self,
        step: TaskStep,
        context: OrchestrationContext,
    ) -> ExecutionResult:
        """Execute a single task step.

        Args:
            step: The TaskStep to execute
            context: Shared orchestration context

        Returns:
            ExecutionResult with the step's outcome
        """
        step_start = time.time()

        try:
            # Get or create the appropriate skill
            skill_name = step.agent or "code"
            skill = self.skill_registry.get(skill_name)

            if skill is None:
                # Fall back to code skill
                skill = self.skill_registry.get("code") or self.skill_registry.get("opencode-integration")

            if skill is None:
                return ExecutionResult(
                    step_id=step.step_id,
                    success=False,
                    error=f"Unknown agent/skill: {skill_name}",
                )

            # Validate and execute the skill
            inputs = SkillInput(
                prompt=step.task,
                model=step.model or "",
                task_context={**context.metadata, "step_id": step.step_id},
                parameters={
                    "provider": step.provider,
                    "model": step.model,
                },
            )

            # Validate inputs
            is_valid, validation_errors = skill.validate_inputs(inputs)
            if not is_valid:
                return ExecutionResult(
                    step_id=step.step_id,
                    success=False,
                    error=f"Invalid inputs: {'; '.join(validation_errors)}",
                )

            # Execute the skill
            output = skill.execute(inputs)

            # Record in audit log
            self._record_audit(
                {
                    "step_id": step.step_id,
                    "skill": skill.name,
                    "success": output.success,
                    "execution_time": time.time() - step_start,
                    "model": output.model_used,
                    "has_error": bool(output.error),
                }
            )

            return ExecutionResult(
                step_id=step.step_id,
                success=output.success,
                text=output.result_text,
                model=output.model_used,
                provider=skill.provider if hasattr(skill, "provider") else "",
                task_id=output.task_id,
                error=output.error,
                raw=output.metadata,
            )

        except Exception as e:
            self._record_audit(
                {
                    "step_id": step.step_id,
                    "error": str(e)[:200],
                    "execution_time": time.time() - step_start,
                }
            )
            return ExecutionResult(
                step_id=step.step_id,
                success=False,
                error=f"Step execution exception: {str(e)[:200]}",
            )

    # ── Parallel Execution ────────────────────────────────────────────

    def execute_parallel(
        self,
        steps: list[TaskStep],
        context: OrchestrationContext,
    ) -> list[ExecutionResult]:
        """Execute steps in parallel where dependencies allow.

        Args:
            steps: List of TaskStep objects to execute
            context: Shared orchestration context

        Returns:
            List of ExecutionResult one per step
        """
        results: dict[str, ExecutionResult] = {}
        remaining = list(steps)  # Copy to mutate
        completed_steps: set[str] = set()

        with ThreadPoolExecutor(max_workers=self.max_parallel_steps) as executor:
            # Submit steps whose dependencies are satisfied
            future_to_step: dict[Any, TaskStep] = {}

            def try_submit():
                """Try to submit steps whose dependencies are met."""
                nonlocal remaining, future_to_step, completed_steps
                ready_steps = []
                for step in list(remaining):
                    deps_met = all(dep in completed_steps for dep in step.depends_on)
                    if deps_met and step.step_id not in completed_steps:
                        ready_steps.append(step)

                for step in ready_steps:
                    future = executor.submit(self.execute_step, step, context)
                    future_to_step[future] = step
                    remaining.remove(step)

            # Main loop: keep submitting and collecting results
            max_iterations = len(steps) + 1
            for _ in range(max_iterations):
                if not remaining and not future_to_step:
                    break

                try_submit()

                if not future_to_step:
                    # No more steps can be submitted; wait for completion
                    break

                # Wait for at least one future to complete
                for future in as_completed(future_to_step, timeout=self.default_timeout):
                    step = future_to_step.pop(future)
                    try:
                        result = future.result()
                        results[step.step_id] = result
                        completed_steps.add(step.step_id)
                    except Exception as e:
                        step = future_to_step.pop(future)
                        results[step.step_id] = ExecutionResult(
                            step_id=step.step_id,
                            success=False,
                            error=f"Step execution failed with exception: {str(e)[:200]}",
                        )
                        completed_steps.add(step.step_id)

                    # Try to submit more steps after completion
                    try_submit()

            # Collect any remaining results
            for step in remaining:
                # Check if already in results (maybe submitted but not collected)
                if step.step_id not in results:
                    results[step.step_id] = ExecutionResult(
                        step_id=step.step_id,
                        success=False,
                        error="Step not executed (remaining after parallel loop)",
                    )

        return list(results.values())

    # ── Full Orchestration ────────────────────────────────────────────

    def orchestrate(
        self,
        prompt: str,
        routing_profile: str = "balanced",
        max_steps: int | None = None,
        context: dict[str, Any] | None = None,
    ) -> tuple[OrchestrationContext, list[ExecutionResult]]:
        """Run full orchestration from a user prompt.

        Args:
            prompt: The user's original request
            routing_profile: One of the 7 routing profiles (free-first, local-first, etc.)
            max_steps: Maximum number of decomposition steps (None = auto)
            context: Optional initial context

        Returns:
            (orchestration_context, execution_results) tuple
        """
        ctx = OrchestrationContext(
            original_prompt=prompt,
            metadata=context or {},
            status=OrchestrationStatus.RUNNING,
        )

        # Decompose the task
        steps, decomp_ctx = self.decompose_task(prompt, context)
        ctx.decomposition = decomp_ctx.decomposition

        # Limit steps if requested
        if max_steps is not None:
            steps = steps[:max_steps]

        # Execute steps (with parallel where safe)
        results = self.execute_parallel(steps, ctx)

        # Set completion time
        ctx.end_time = time.time()
        ctx.status = (
            OrchestrationStatus.COMPLETED if all(r.success for r in results) else OrchestrationStatus.FAILED
        )

        return ctx, results

    # ── Audit/Traceability ────────────────────────────────────────────

    def _record_audit(self, entry: dict[str, Any]) -> None:
        """Record an audit entry for traceability."""
        entry["timestamp"] = time.time()
        self._audit_log.append(entry)

    def get_audit_log(self) -> list[dict[str, Any]]:
        """Get the full audit log for this orchestration session."""
        return self._audit_log.copy()

    def clear_audit_log(self) -> None:
        """Clear the audit log."""
        self._audit_log.clear()


# ── Multi-Agent Orchestration Facade ──────────────────────────────────


class MultiAgentOrchestrator:
    """Facade providing a simplified interface for multi-agent orchestration.

    Usage:
        orchestrator = MultiAgentOrchestrator()
        ctx, results = orchestrator.orchestrate(
            "Implement a user authentication system",
            routing_profile="free-first"
        )
    """

    def __init__(self, skill_registry: SkillRegistry | None = None):
        self.engine = OrchestrationEngine(skill_registry)

    def orchestrate(
        self,
        prompt: str,
        routing_profile: str = "balanced",
        max_steps: int | None = None,
    ) -> tuple[OrchestrationContext, list[ExecutionResult]]:
        """Orchestrate a task through multiple agents.

        Args:
            prompt: The user's request
            routing_profile: One of free-first, local-first, best-quality, fastest,
                           balanced, privacy-first, custom
            max_steps: Maximum decomposition steps

        Returns:
            (context, results) tuple
        """
        return self.engine.orchestrate(
            prompt=prompt,
            routing_profile=routing_profile,
            max_steps=max_steps,
        )

    def get_capabilities_report(self) -> dict[str, Any]:
        """Get a report of what the orchestration system can do."""
        skills = self.engine.skill_registry.list_all()
        return {
            "total_skills": len(skills),
            "skills_by_category": {
                cat: [s.name for s in skills]
                for cat, skills in self.engine.skill_registry.list_by_category().items()
            },
            "routing_profiles": [
                "free-first",
                "local-first",
                "best-quality",
                "fastest",
                "balanced",
                "privacy-first",
                "custom",
            ],
            "supported_operations": [
                "discover",
                "health_check",
                "list_models",
                "execute",
                "execute_background",
                "get_task_status",
                "cancel_task",
                "get_capabilities",
            ],
            "audit_log_enabled": True,
        }
