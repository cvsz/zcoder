"""zGPU Benchmark Suite: Parallel Vector Addition (SAXPY) and Matrix Multiplication (GEMM)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from zgpu.isa.assembler import Assembler
from zgpu.simulator.gpu import ZGPU
from zgpu.simulator.sm import bits_to_f32, f32_to_bits


def benchmark_vector_add():
    print("==================================================")
    print("▶ Software Simulator Benchmark 1: Vector Add (1024 elements)")
    print("==================================================")

    # Assembly kernel: out[tid] = a[tid] + b[tid]
    # R0 = block_id * 256 + thread_id within block
    # R2 = addr_a = tid * 4
    # R3 = addr_b = 4096 + tid * 4
    # R4 = addr_c = 8192 + tid * 4
    kernel_src = """
    GET.TID R0
    GET.BID R12
    VMUL R12, R12, R13   # block base = block_id * 256 threads
    VADD R0, R0, R12     # global element index

    # R1 = 4 (byte width)
    # Compute base offsets
    VMUL R2, R0, R1      # R2 = tid * 4
    VADD R3, R2, R10     # R3 = base_b + offset
    VADD R4, R2, R11     # R4 = base_c + offset

    # Load vectors from global memory
    VLOAD.G R5, R2, 0    # R5 = load a[tid]
    VLOAD.G R6, R3, 0    # R6 = load b[tid]

    # Vector FP32 Add
    VFADD R7, R5, R6     # R7 = a + b

    # Store result to global memory
    VSTORE.G R4, R7, 0   # c[tid] = R7
    HALT
    """

    bytecode = Assembler.assemble(kernel_src)
    gpu = ZGPU(num_sms=4)

    # Setup host data
    n_elements = 1024
    base_a = 0
    base_b = 4096
    base_c = 8192

    for i in range(n_elements):
        gpu.global_mem.write_f32(base_a + i * 4, float(i * 1.5))
        gpu.global_mem.write_f32(base_b + i * 4, float(i * 2.5))
    gpu.global_mem.read_transactions = 0
    gpu.global_mem.write_transactions = 0

    # Four blocks of eight warps cover 1024 lanes across four SMs.
    warps_per_block = 8

    def init_constants(sm, sm_index):
        for w in sm.warps:
            for lane in range(32):
                w.rf[lane][1] = 4
                w.rf[lane][10] = base_b
                w.rf[lane][11] = base_c
                w.rf[lane][13] = warps_per_block * 32

    # Launch kernel: 1024 threads = four blocks of 256 threads.
    for sm_index, sm in enumerate(gpu.sms):
        sm.launch_warps(num_warps=warps_per_block, block_id=sm_index)
        init_constants(sm, sm_index)

    while any(not sm.is_finished() for sm in gpu.sms):
        for sm in gpu.sms:
            if not sm.is_finished():
                sm.step_cycle(bytecode)
        gpu.total_cycles += 1

    perf = gpu.get_performance_counters()

    # Verify results
    correct = 0
    for i in range(n_elements):
        c_val = gpu.global_mem.read_f32(base_c + i * 4)
        expected = (i * 1.5) + (i * 2.5)
        if abs(c_val - expected) < 1e-4:
            correct += 1

    if correct != n_elements:
        raise RuntimeError(f"vector-add benchmark validation failed: {correct}/{n_elements} elements correct")
    print(f"Validation: {correct}/{n_elements} elements correct (100% precision).")
    print("Performance Counters:")
    for k, v in perf.items():
        print(f"  • {k}: {v}")


def benchmark_tensor_mma():
    print("\n==================================================")
    print("▶ Software Simulator Benchmark 2: 4x4 MMA GEMM")
    print("==================================================")

    # MMA.SYNC D, A, B, C computes D = A x B + C
    kernel_src = """
    MMA.SYNC R10, R1, R2, R3
    HALT
    """

    bytecode = Assembler.assemble(kernel_src)
    gpu = ZGPU(num_sms=1)
    sm = gpu.sms[0]
    sm.launch_warps(num_warps=1, block_id=0)
    warp = sm.warps[0]

    # Initialize 4x4 matrix A and B across 16 lanes
    # A = identity 4x4, B = all 2.0, C = all 0.5
    for r in range(4):
        for c in range(4):
            lane = r * 4 + c
            warp.rf[lane][1] = f32_to_bits(1.0 if r == c else 0.0)
            warp.rf[lane][2] = f32_to_bits(2.0)
            warp.rf[lane][3] = f32_to_bits(0.5)

    while not sm.is_finished():
        sm.step_cycle(bytecode)
        gpu.total_cycles += 1

    # D = I * 2.0 + 0.5 = 2.5
    res = [bits_to_f32(warp.rf[i][10]) for i in range(16)]
    print("Result Matrix Tile (4x4):")
    for r in range(4):
        row_str = " ".join(f"{res[r * 4 + c]:.2f}" for c in range(4))
        print(f"  [ {row_str} ]")

    if not all(abs(val - 2.5) < 1e-5 for val in res):
        raise RuntimeError("simulated 4x4 MMA benchmark validation failed")
    print("Simulated MMA verification PASSED!")


if __name__ == "__main__":
    benchmark_vector_add()
    benchmark_tensor_mma()
