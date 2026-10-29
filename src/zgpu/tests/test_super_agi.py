import pytest

from zgpu.agi.agent_core import SuperAGIAgent
from zgpu.agi.planner import SuperAGIPlanner, ThoughtCandidate
from zgpu.agi.vector_memory import FastVectorMemory
from zgpu.runtime.runtime import ZRuntime


def test_fast_vector_memory():
    rt = ZRuntime()
    mem = FastVectorMemory(dim=16, runtime=rt)

    vec_a = [1.0] + [0.0] * 15
    vec_b = [0.0, 1.0] + [0.0] * 14
    vec_c = [0.707, 0.707] + [0.0] * 14

    mem.add("mem_a", vec_a, {"tag": "A"})
    mem.add("mem_b", vec_b, {"tag": "B"})
    mem.add("mem_c", vec_c, {"tag": "C"})

    assert mem.count() == 3

    # Query closest to vec_a
    results = mem.search(vec_a, top_k=2)
    assert len(results) == 2
    top_record, score = results[0]
    assert top_record.id == "mem_a"
    assert pytest.approx(score, rel=1e-2) == 1.0


def test_super_agi_planner():
    rt = ZRuntime()
    planner = SuperAGIPlanner(feature_dim=16, runtime=rt)
    planner.set_objective([1.0] + [0.0] * 15)

    candidates = [
        ThoughtCandidate("cand_0", "action_0", [0.1] * 16),
        ThoughtCandidate("cand_best", "action_best", [1.0] + [0.0] * 15),
        ThoughtCandidate("cand_low", "action_low", [-0.5] + [0.0] * 15),
    ]

    best = planner.select_best_path(candidates)
    assert best is not None
    assert best.thought_id == "cand_best"
    assert best.score > 0.9


def test_super_agi_agent_execution():
    rt = ZRuntime()
    agent = SuperAGIAgent("Agent-Test", d_model=16, runtime=rt)

    # Register custom tool
    agent.register_tool("solve_math", lambda param: f"Calculated: {param}")

    step_res = agent.step("solve_math: 2+2")
    assert step_res.step_num == 1
    assert step_res.action is not None
    assert step_res.latency_ms > 0
    assert agent.memory.count() == 1

    # Run multi-step goal
    results = agent.run_goal("Achieve target", max_steps=2)
    assert len(results) == 2
    assert agent.memory.count() == 3
