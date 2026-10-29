"""zGPU Distributed Tensor Parallelism (TP) & All-Reduce Crossbar Engine.

Decomposes large Linear projection matrices across multiple virtual zGPU devices
and performs peer-to-peer All-Reduce collective communications over zLink.
"""

from __future__ import annotations

from zgpu.kernels.llm_kernels import LLMKernels
from zgpu.runtime.runtime import ZRuntime


class DistributedCrossbar:
    """Simulates multi-GPU zLink high-speed coherent interconnect."""

    def __init__(self, world_size: int = 2):
        self.world_size = world_size
        self.runtimes = [ZRuntime() for _ in range(world_size)]
        self.kernels = [LLMKernels(rt) for rt in self.runtimes]

    def all_reduce(self, shards: list[list[list[float]]]) -> list[list[list[float]]]:
        """Performs hardware All-Reduce SUM across all participating device shards."""
        assert len(shards) == self.world_size
        rows = len(shards[0])
        cols = len(shards[0][0])

        reduced = [[0.0 for _ in range(cols)] for _ in range(rows)]
        for rank in range(self.world_size):
            for r in range(rows):
                for c in range(cols):
                    reduced[r][c] += shards[rank][r][c]

        # Broadcast reduced result back to all devices
        return [list([list(row) for row in reduced]) for _ in range(self.world_size)]


class ColumnParallelLinear:
    """Linear layer partitioned column-wise across zGPU devices (Megatron TP style)."""

    def __init__(self, in_features: int, out_features: int, crossbar: DistributedCrossbar):
        self.in_features = in_features
        self.out_features = out_features
        self.crossbar = crossbar
        self.world_size = crossbar.world_size
        self.shard_out = out_features // self.world_size

        # Sharded weights for each device rank
        self.weight_shards = []
        for rank in range(self.world_size):
            shard = [[0.01 * ((i + j + rank) % 5) for j in range(in_features)] for i in range(self.shard_out)]
            self.weight_shards.append(shard)

    def forward(self, x: list[list[float]]) -> list[list[list[float]]]:
        """Returns sharded output for each device rank."""
        outputs = []
        for rank in range(self.world_size):
            w_shard = self.weight_shards[rank]
            # Transpose shard for GEMM: (in_features x shard_out)
            w_t = [[w_shard[r][c] for r in range(self.shard_out)] for c in range(self.in_features)]
            out_rank = self.crossbar.kernels[rank].gemm(x, w_t)
            outputs.append(out_rank)
        return outputs


class RowParallelLinear:
    """Linear layer partitioned row-wise across zGPU devices followed by All-Reduce."""

    def __init__(self, in_features: int, out_features: int, crossbar: DistributedCrossbar):
        self.in_features = in_features
        self.out_features = out_features
        self.crossbar = crossbar
        self.world_size = crossbar.world_size
        self.shard_in = in_features // self.world_size

        # Sharded weights for each device rank: (out_features x shard_in)
        self.weight_shards = []
        for rank in range(self.world_size):
            shard = [[0.01 * ((i + j + rank) % 5) for j in range(self.shard_in)] for i in range(out_features)]
            self.weight_shards.append(shard)

    def forward(self, x_shards: list[list[list[float]]]) -> list[list[float]]:
        """Computes partial products on each device and performs All-Reduce."""
        partial_products = []
        for rank in range(self.world_size):
            w_shard = self.weight_shards[rank]
            x_rank = x_shards[rank]
            # Transpose weight shard: (shard_in x out_features)
            w_t = [[w_shard[r][c] for r in range(self.out_features)] for c in range(self.shard_in)]
            part = self.crossbar.kernels[rank].gemm(x_rank, w_t)
            partial_products.append(part)

        # All-Reduce collective summation over zLink crossbar
        reduced_all = self.crossbar.all_reduce(partial_products)
        return reduced_all[0]
