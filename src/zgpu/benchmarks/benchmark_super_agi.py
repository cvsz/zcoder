"""SuperAGI Autonomous Agent Latency & Throughput Benchmark on zGPU."""

from __future__ import annotations

import time

from zgpu.agi.agent_core import SuperAGIAgent
from zgpu.runtime.runtime import ZRuntime


def run_super_agi_benchmark():
    print("=" * 65)
    print("🧠 zGPU Hardware-Accelerated SuperAGI Autonomous Benchmark")
    print("=" * 65)

    rt = ZRuntime()
    agent = SuperAGIAgent(agent_name="SuperAGI-Apex", d_model=16, runtime=rt)

    # Pre-populate memory bank with 32 historical context records
    for i in range(32):
        vec = [0.1 * ((i * 7 + j) % 11 - 5) for j in range(16)]
        agent.memory.add(f"context_{i}", vec, {"idx": i})

    print(f"• Pre-loaded Associative Vector Memory Records: {agent.memory.count()}")

    # Measure autonomous perception-planning-action loop
    num_steps = 5
    t0 = time.perf_counter()
    results = agent.run_goal("Execute high-frequency trading & reasoning", max_steps=num_steps)
    total_time = time.perf_counter() - t0

    avg_step_ms = (total_time / num_steps) * 1000.0
    steps_per_sec = num_steps / total_time

    print(f"• Completed Autonomous Execution Steps: {num_steps}")
    print(f"• Total Execution Time: {total_time * 1000.0:.2f} ms")
    print(f"• Latency per Autonomous Step: {avg_step_ms:.2f} ms")
    print(f"• Autonomous AGI Step Throughput: {steps_per_sec:.2f} steps/second")

    for res in results:
        print(f"   [Step {res.step_num}] {res.thought} -> Action: {res.action} ({res.latency_ms:.1f} ms)")

    print("\n✅ SuperAGI Hardware-Accelerated Benchmark Complete!")
    print("=" * 65)


if __name__ == "__main__":
    run_super_agi_benchmark()
