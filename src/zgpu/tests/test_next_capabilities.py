import pytest

from zgpu.agi.swarm import SuperAGISwarm
from zgpu.distributed.tensor_parallel import ColumnParallelLinear, DistributedCrossbar, RowParallelLinear
from zgpu.kernels.flash_attn.flash_attention import FlashAttention3Kernel
from zgpu.llm.speculative.engine import SpeculativeDecoder
from zgpu.llm.transformer import ZGPULLM, LLMConfig
from zgpu.runtime.runtime import ZRuntime
from zgpu.torch_compat.tensor import ZTensor


def test_flash_attention_3():
    kernel = FlashAttention3Kernel(d_model=4, block_size=2)
    # Sequence length 4, d_model 4
    Q = [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]]
    K = [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]]
    V = [[2.0, 0.0, 0.0, 0.0], [0.0, 2.0, 0.0, 0.0], [0.0, 0.0, 2.0, 0.0], [0.0, 0.0, 0.0, 2.0]]

    out = kernel.forward(Q, K, V, causal=True)
    assert len(out) == 4
    assert len(out[0]) == 4
    # First token only attends to itself, so value should be V[0] = [2.0, 0.0, 0.0, 0.0]
    assert pytest.approx(out[0][0], rel=1e-3) == 2.0


def test_speculative_decoding():
    rt = ZRuntime()
    cfg_target = LLMConfig(vocab_size=32, d_model=8, num_layers=2)
    cfg_draft = LLMConfig(vocab_size=32, d_model=8, num_layers=1)

    target_model = ZGPULLM(config=cfg_target, runtime=rt)
    draft_model = ZGPULLM(config=cfg_draft, runtime=rt)

    decoder = SpeculativeDecoder(target_model, draft_model, lookahead_k=2)
    res = decoder.generate(prompt_tokens=[1, 2], max_new_tokens=4)
    assert len(res.tokens) >= 6
    assert res.accepted_tokens > 0


def test_distributed_tensor_parallelism():
    crossbar = DistributedCrossbar(world_size=2)
    col_linear = ColumnParallelLinear(in_features=4, out_features=8, crossbar=crossbar)
    row_linear = RowParallelLinear(in_features=8, out_features=4, crossbar=crossbar)

    x = [[1.0, 1.0, 1.0, 1.0]]
    # Column parallel splits output: returns 2 shards of (1 x 4)
    shards = col_linear.forward(x)
    assert len(shards) == 2
    assert len(shards[0][0]) == 4

    # Row parallel reduces shards back to (1 x 4)
    out = row_linear.forward(shards)
    assert len(out) == 1
    assert len(out[0]) == 4


def test_torch_compat_ztensor():
    rt = ZRuntime()
    data = [1.0, 2.0, 3.0, 4.0]
    t = ZTensor(data, shape=(2, 2), runtime=rt)
    assert t.shape == (2, 2)
    assert t.__zgpu_array_interface__["typestr"] == "<f4"

    readback = t.to_list()
    assert readback == data


def test_super_agi_swarm():
    swarm = SuperAGISwarm(shared_memory_dim=16)
    swarm.spawn_agent("Planner")
    swarm.spawn_agent("Coder")
    swarm.spawn_agent("Verifier")

    res = swarm.execute_swarm_task("Build parallel matrix multiplier")
    assert res["status"] == "completed"
    assert res["total_messages"] >= 3
    assert swarm.shared_memory.count() >= 3
