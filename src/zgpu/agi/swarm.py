"""SuperAGI Autonomous Multi-Agent Swarm Framework.

Enables distributed swarms of autonomous agents (Planner, Coder, Reviewer, Verifier)
to collaborate over a shared associative vector memory and peer-to-peer message crossbar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from zgpu.agi.agent_core import SuperAGIAgent
from zgpu.agi.vector_memory import FastVectorMemory
from zgpu.runtime.runtime import ZRuntime


@dataclass
class SwarmMessage:
    sender: str
    recipient: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


class SuperAGISwarm:
    """Collaborative multi-agent swarm running on zGPU."""

    def __init__(self, shared_memory_dim: int = 16, runtime: ZRuntime | None = None):
        self.runtime = runtime or ZRuntime()
        self.shared_memory = FastVectorMemory(dim=shared_memory_dim, runtime=self.runtime)
        self.agents: dict[str, SuperAGIAgent] = {}
        self.message_bus: list[SwarmMessage] = []

    def spawn_agent(self, role_name: str) -> SuperAGIAgent:
        """Create a specialized role agent connected to the swarm."""
        agent = SuperAGIAgent(agent_name=role_name, d_model=self.shared_memory.dim, runtime=self.runtime)
        # Bind shared memory
        agent.memory = self.shared_memory
        self.agents[role_name] = agent
        return agent

    def broadcast(self, sender: str, content: str):
        msg = SwarmMessage(sender=sender, recipient="all", content=content)
        self.message_bus.append(msg)

    def execute_swarm_task(self, task_description: str) -> dict[str, Any]:
        """Execute a coordinated multi-agent workflow: Planner -> Coder -> Verifier."""
        if not self.agents:
            self.spawn_agent("Planner")
            self.spawn_agent("Coder")
            self.spawn_agent("Verifier")

        planner = self.agents["Planner"]
        coder = self.agents["Coder"]
        verifier = self.agents["Verifier"]

        # Step 1: Planning
        plan_res = planner.step(f"Plan solution for: {task_description}")
        self.broadcast("Planner", f"Plan formed: {plan_res.thought}")

        # Step 2: Coding
        coder_res = coder.step(f"Implement plan: {plan_res.thought}")
        self.broadcast("Coder", f"Implementation produced: {coder_res.action}")

        # Step 3: Verification
        verifier_res = verifier.step(f"Verify execution outcome: {coder_res.observation}")
        self.broadcast("Verifier", f"Verification complete: score={verifier_res.score}")

        return {
            "task": task_description,
            "status": "completed",
            "plan": plan_res.thought,
            "action": coder_res.action,
            "verification": verifier_res.observation,
            "total_messages": len(self.message_bus),
        }
