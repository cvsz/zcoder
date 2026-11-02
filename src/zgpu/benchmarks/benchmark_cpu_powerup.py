"""Heterogeneous zGPU + Network CPU Powerup Benchmark."""

from __future__ import annotations

import time

from zgpu.cluster.network_pool import NetworkCPUPool
from zgpu.cluster.worker.cpu_worker import CPUComputeEngine
from zgpu.runtime.runtime import ZRuntime


def run_powerup_benchmark():
    print("=" * 65)
    print("⚡ zGPU + Network CPU Heterogeneous Powerup Benchmark")
    print("=" * 65)

    rt = ZRuntime()
    pool = NetworkCPUPool(runtime=rt)

    # Matrix sizes: 32x32
    M, K, N = 32, 32, 32
    A = [[1.0 for _ in range(K)] for _ in range(M)]
    B = [[2.0 for _ in range(N)] for _ in range(K)]

    # 1. Local zGPU Baseline
    t0 = time.perf_counter()
    pool.kernels.gemm(A, B)
    t_zgpu = (time.perf_counter() - t0) * 1000.0

    print(f"• Baseline Pure zGPU (32x32 GEMM): {t_zgpu:.2f} ms")

    # 2. Local CPU Engine Chunk
    t0 = time.perf_counter()
    CPUComputeEngine.gemm_chunk(A[:16], B)
    t_cpu = (time.perf_counter() - t0) * 1000.0

    print(f"• Local CPU Worker Chunk (16x32 GEMM): {t_cpu:.2f} ms")

    # 3. Hybrid Partitioned GEMM
    # In-memory mock node for benchmark
    class MockRemoteNode:
        active = True
        node_id = "bench_node"

    pool.nodes["bench_node"] = MockRemoteNode()
    pool.dispatch_remote_gemm = lambda nid, achunk, bmat: CPUComputeEngine.gemm_chunk(achunk, bmat)

    t0 = time.perf_counter()
    hybrid_res = pool.hybrid_gemm_powerup(A, B, gpu_fraction=0.5)
    t_hybrid = (time.perf_counter() - t0) * 1000.0

    print(f"• Heterogeneous Powerup Hybrid (50% GPU + 50% CPU): {t_hybrid:.2f} ms")
    print(f"• Hybrid Verification: C[0][0] = {hybrid_res[0][0]:.1f} (Expected: 64.0)")

    print("\n✅ Heterogeneous Compute Powerup Benchmark Complete!")
    print("=" * 65)


if __name__ == "__main__":
    run_powerup_benchmark()
