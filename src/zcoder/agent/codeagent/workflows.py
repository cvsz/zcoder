"""Dynamic Workflows / Ultracode — Claude Code-compatible workflow orchestration.

Ultracode is a session setting that triggers automatic workflow orchestration
for each substantive task. Including the keyword ``ultracode`` in a prompt also
opts a single task into workflow mode.

Workflows orchestrate many subagents using three primitives:

  * agent(prompt, opts)        — spawn one subagent, returns its summary
  * pipeline(items, fn)        — run one agent per item in a list, returns list
  * parallel(tasks)            — run multiple agents simultaneously, returns list

All primitives are async and run subagents in isolated context via SubagentRunner.

zcoder runs entirely on loopback local inference — no hosted model calls.
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from typing import Any

_ULTRA_KEYWORD = re.compile(r"\bultracode\b", re.IGNORECASE)

# Workflow size guidelines (agent count Claude aims for)
_SIZE_GUIDELINES = {"unrestricted": None, "small": 5, "medium": 10, "large": 50}
_MAX_PARALLEL_ITEMS = 4096
_DEFAULT_MAX_CONCURRENT = 16


@dataclass
class WorkflowAgentResult:
    """Result from a single workflow agent() call."""

    label: str | None
    output: str | None
    success: bool
    error: str | None = None


@dataclass
class WorkflowPhase:
    """A named group of agents in a workflow."""

    title: str
    agents: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class WorkflowRun:
    """A running or completed workflow."""

    name: str
    status: str  # pending | running | completed | failed | stopped
    phases: list[WorkflowPhase] = field(default_factory=list)
    results: list[WorkflowAgentResult] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    agent_count: int = 0
    token_usage: int = 0


class WorkflowEngine:
    """Executes workflow scripts with agent(), pipeline(), parallel() primitives."""

    def __init__(
        self,
        llm: Any,
        ws: Any,
        policy: Any,
        registry: Any,
        max_concurrent: int = _DEFAULT_MAX_CONCURRENT,
    ):
        self.llm = llm
        self.ws = ws
        self.policy = policy
        self.registry = registry
        self.max_concurrent = max_concurrent

    # --- public API -------------------------------------------------------

    async def run_script(
        self,
        script: str,
        args: Any = None,
        size_guideline: str = "medium",
    ) -> WorkflowRun:
        """Execute a workflow script.

        The script must define an async ``main()`` function that calls the
        provided primitives: agent(), pipeline(), parallel(), phase(), log().
        """
        agent_count = 0
        results: list[WorkflowAgentResult] = []
        phases: list[WorkflowPhase] = []

        # Build the primitive namespace
        ns: dict[str, Any] = {}

        async def agent(prompt: str, opts: dict[str, Any] | None = None) -> str | None:
            nonlocal agent_count
            opts = opts or {}
            from zcoder.agent.codeagent.subagents import SubagentRunner

            runner = SubagentRunner(self.llm, self.ws, self.policy, self.registry)
            result = await runner.run(
                agent_type=opts.get("agent_type", "General"),
                prompt=prompt,
                tools=opts.get("tools"),
                model=opts.get("model"),
                permission_mode=opts.get("permission_mode"),
                max_turns=opts.get("max_turns"),
            )
            agent_count += 1
            entry = WorkflowAgentResult(
                label=opts.get("label"),
                output=result.summary,
                success=result.success,
                error=None if result.success else "blocked",
            )
            results.append(entry)
            if phases:
                phases[-1].agents.append({"label": opts.get("label"), "success": result.success})
            return result.summary if result.success else None

        async def pipeline(items: list[Any], fn: Any) -> list[str | None]:
            if len(items) > _MAX_PARALLEL_ITEMS:
                raise ValueError(f"pipeline() exceeds {_MAX_PARALLEL_ITEMS} item limit")
            outputs: list[str | None] = []
            for item in items:
                prompt = str(fn(item)) if callable(fn) else str(fn).replace("{}", str(item))
                out = await agent(prompt, {})
                outputs.append(out)
            return outputs

        async def parallel(tasks: list[dict[str, Any]]) -> list[str | None]:
            if len(tasks) > self.max_concurrent:
                raise ValueError(f"parallel() exceeds {self.max_concurrent} concurrent limit")
            coros = [agent(t.get("prompt", ""), t.get("opts", {})) for t in tasks]
            return await asyncio.gather(*coros)

        def phase(title: str) -> WorkflowPhase:
            p = WorkflowPhase(title=title)
            phases.append(p)
            return p

        def log(message: str) -> None:
            print(f"[workflow] {message}")

        ns = {
            "agent": agent,
            "pipeline": pipeline,
            "parallel": parallel,
            "phase": phase,
            "log": log,
            "args": args,
        }

        # Execute the script: it should define main()
        try:
            exec(
                compile(script, "<workflow>", "exec"), ns
            )  # nosec B102 — user-provided workflow script (documented feature)
        except Exception:
            return WorkflowRun(
                name="workflow",
                status="failed",
                phases=phases,
                results=results,
                agent_count=agent_count,
            )

        main = ns.get("main")
        if not main or not asyncio.iscoroutinefunction(main):
            return WorkflowRun(
                name="workflow",
                status="failed",
                phases=phases,
                results=results,
                agent_count=agent_count,
            )

        try:
            await main()
        except Exception:
            return WorkflowRun(
                name="workflow",
                status="failed",
                phases=phases,
                results=results,
                agent_count=agent_count,
            )

        return WorkflowRun(
            name="workflow",
            status="completed",
            phases=phases,
            results=results,
            agent_count=agent_count,
        )


def is_ultracode_prompt(text: str) -> bool:
    """Return True if the prompt contains the ultracode keyword."""
    return bool(_ULTRA_KEYWORD.search(text))


def strip_ultracode_keyword(text: str) -> str:
    """Remove the ultracode keyword from a prompt."""
    return _ULTRA_KEYWORD.sub("", text).strip()


def default_workflow_script(task: str) -> str:
    """Generate a default workflow script for a task.

    This is what Claude Code would write automatically when ultracode is on.
    """
    return f"""async def main():
    log("Starting workflow for: {task}")

    # Phase 1: Research
    phase("Research")
    research = await agent(
        "Research the codebase to understand: {task}",
        {{"label": "research", "agent_type": "Explore"}}
    )

    # Phase 2: Plan
    phase("Plan")
    plan = await agent(
        "Based on this research: {{research}}\\n\\nCreate a plan to: {task}",
        {{"label": "plan", "agent_type": "Plan"}}
    )

    # Phase 3: Implement
    phase("Implement")
    result = await agent(
        "Implement this plan: {{plan}}",
        {{"label": "implement", "agent_type": "General"}}
    )

    # Phase 4: Verify
    phase("Verify")
    verify = await agent(
        "Verify this implementation against the plan: {{plan}}\\n\\nResult: {{result}}",
        {{"label": "verify", "agent_type": "General"}}
    )

    log("Workflow complete")
    return verify
"""
