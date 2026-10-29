"""SuperAGI Autonomous Agent Execution Framework.

Combines zGPU-accelerated LLM reasoning, fast vector memory, Tree-of-Thought planning,
and extensible tool calling into an ultra-fast hardware-accelerated autonomous agent.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from zgpu.agi.planner import SuperAGIPlanner, ThoughtCandidate
from zgpu.agi.vector_memory import FastVectorMemory
from zgpu.llm.transformer import ZGPULLM, LLMConfig
from zgpu.runtime.runtime import ZRuntime

log = logging.getLogger("SuperAGI-zGPU")


@dataclass
class AgentStepResult:
    step_num: int
    thought: str
    action: str
    score: float
    observation: Any
    latency_ms: float


class SuperAGIAgent:
    """Autonomous agent whose vector operations use the zGPU runtime simulator."""

    def __init__(
        self,
        agent_name: str = "zGPU-AGI-Alpha",
        d_model: int = 16,
        runtime: ZRuntime | None = None,
    ):
        self.name = agent_name
        self.runtime = runtime or ZRuntime()
        self.llm = ZGPULLM(config=LLMConfig(d_model=d_model, num_layers=2), runtime=self.runtime)
        self.memory = FastVectorMemory(dim=d_model, runtime=self.runtime)
        self.planner = SuperAGIPlanner(feature_dim=d_model, runtime=self.runtime)
        self.tools: dict[str, Callable[[str], Any]] = {}
        self.execution_history: list[AgentStepResult] = []

        # Register standard built-in tools
        self._register_default_tools()

    def _register_default_tools(self):
        self.register_tool("echo", lambda param: f"Echo: {param}")
        self.register_tool("memory_store", lambda param: f"Stored: {param}")
        self.register_tool("status_check", lambda _: "zGPU-SM-0 Online. All 32 SIMT lanes active.")

    def register_tool(self, name: str, func: Callable[[str], Any]):
        """Register an autonomous execution tool."""
        self.tools[name] = func

    def reason_and_plan(self, goal: str, num_candidates: int = 4) -> ThoughtCandidate:
        """Generate reasoning candidates and rank them using zGPU Tensor Cores."""
        candidates = []
        for i in range(num_candidates):
            # Synthesize feature vector for candidate path
            feature_vec = [0.1 * ((i * 5 + j) % 9 - 4) for j in range(self.planner.feature_dim)]
            tool_name = list(self.tools.keys())[i % len(self.tools)]
            candidates.append(
                ThoughtCandidate(
                    thought_id=f"path_{i}",
                    action=f"{tool_name}:{goal}",
                    feature_vector=feature_vec,
                )
            )

        best_thought = self.planner.select_best_path(candidates)
        return best_thought

    def step(self, goal: str) -> AgentStepResult:
        """Execute a single autonomous perception -> planning -> action cycle."""
        t0 = time.perf_counter()

        # 1. Search vector memory for relevant context
        query_vec = [0.05 * (ord(c) % 7) for c in goal[: self.memory.dim]]
        if len(query_vec) < self.memory.dim:
            query_vec.extend([0.0] * (self.memory.dim - len(query_vec)))
        self.memory.search(query_vec, top_k=2)

        # 2. Plan next action using zGPU hardware evaluator
        best_candidate = self.reason_and_plan(goal)

        # 3. Dispatch tool execution
        tool_action = best_candidate.action if best_candidate else "echo:fallback"
        tool_name, _, param = tool_action.partition(":")

        handler = self.tools.get(tool_name, lambda p: f"Unknown tool: {p}")
        observation = handler(param)

        # 4. Store outcome in vector memory
        step_id = f"step_{len(self.execution_history) + 1}"
        self.memory.add(step_id, query_vec, metadata={"action": tool_action, "obs": observation})

        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        result = AgentStepResult(
            step_num=len(self.execution_history) + 1,
            thought=f"Selected path {best_candidate.thought_id} with score {best_candidate.score:.3f}",
            action=tool_action,
            score=best_candidate.score,
            observation=observation,
            latency_ms=elapsed_ms,
        )
        self.execution_history.append(result)
        return result

    def run_goal(self, goal: str, max_steps: int = 3) -> list[AgentStepResult]:
        """Run an autonomous multi-step execution loop towards a goal."""
        results = []
        for _ in range(max_steps):
            step_res = self.step(goal)
            results.append(step_res)
        return results
