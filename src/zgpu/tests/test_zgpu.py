"""Unit tests for zGPU ISA, SIMT Divergence, Memory Coalescing, and Execution."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from zgpu.isa.assembler import Assembler
from zgpu.isa.instructions import Instruction, Opcode
from zgpu.simulator.gpu import ZGPU, SimulationLimitError
from zgpu.simulator.memory import GlobalMemory, SharedMemory
from zgpu.simulator.sm import bits_to_f32, f32_to_bits


def test_instruction_encode_rejects_fields_that_would_be_truncated():
    with pytest.raises(ValueError, match="destination field"):
        Instruction(op=Opcode.VADD, rd=128).encode()
    with pytest.raises(ValueError, match="5-bit register field"):
        Instruction(op=Opcode.VADD, rs1=32).encode()
    with pytest.raises(ValueError, match="signed 8-bit field"):
        Instruction(op=Opcode.VLOAD_G, imm=128).encode()


def test_instruction_encode_preserves_signed_immediate_boundaries():
    for immediate in (-128, -1, 0, 127):
        encoded = Instruction(op=Opcode.VLOAD_G, imm=immediate).encode()
        assert Instruction.decode(encoded).imm == immediate


@pytest.mark.parametrize("source", ["HALT R0", "VADD R1, R2", "VADD R1, R2, R3, R4", "GET.TID"])
def test_assembler_rejects_missing_or_extra_operands(source):
    with pytest.raises(ValueError):
        Assembler.assemble(source)


@pytest.mark.parametrize("source", ["GET.TID R128", "VADD R1, R32, R2", "VLOAD.G R1, R2, 128"])
def test_assembler_rejects_operands_that_exceed_encoded_fields(source):
    with pytest.raises(ValueError):
        Assembler.assemble(source)


def test_instruction_encode_decode():
    inst = Instruction(op=Opcode.VADD, rd=5, rs1=2, rs2=3)
    encoded = inst.encode()
    decoded = Instruction.decode(encoded)
    assert decoded.op == Opcode.VADD
    assert decoded.rd == 5
    assert decoded.rs1 == 2
    assert decoded.rs2 == 3


@pytest.mark.parametrize("word", [-1, 0x1_0000_0000, True, 1.0, "0"])
def test_instruction_decode_rejects_non_u32_words(word):
    with pytest.raises(ValueError, match="unsigned 32-bit"):
        Instruction.decode(word)


def test_instruction_decode_rejects_unknown_opcode_instead_of_treating_it_as_nop():
    with pytest.raises(ValueError, match="unknown zISA opcode"):
        Instruction.decode(0x00000007)


def test_simt_warp_divergence():
    # If lane is odd (R1=1) -> add 10, else (R1=0) -> add 20
    # BRA.DIV branches to THEN_LABEL if R1 != 0, while pushing fallthrough to stack
    kernel = """
    BRA.DIV THEN_LABEL, R1
    # Fallthrough path: R1 == 0 (even lanes)
    VADD R3, R3, R20
    BRA END_LABEL
    THEN_LABEL:
    # Taken path: R1 == 1 (odd lanes)
    VADD R3, R3, R10
    END_LABEL:
    JOIN
    HALT
    """
    bytecode = Assembler.assemble(kernel)
    gpu = ZGPU(num_sms=1)
    sm = gpu.sms[0]
    sm.launch_warps(1)
    warp = sm.warps[0]

    for lane in range(32):
        warp.rf[lane][1] = 1 if (lane % 2 == 1) else 0  # condition
        warp.rf[lane][3] = 0
        warp.rf[lane][10] = 10
        warp.rf[lane][20] = 20

    while not sm.is_finished():
        sm.step_cycle(bytecode)

    for lane in range(32):
        expected = 10 if (lane % 2 == 1) else 20
        assert warp.rf[lane][3] == expected


def test_gpu_launch_accepts_bounded_execution_and_32_lane_register_inputs():
    gpu = ZGPU(num_sms=1, global_mem_mb=1)
    program = Assembler.assemble("VADD R3, R1, R2\nHALT")

    gpu.launch_kernel(
        program,
        grid_dim=1,
        block_dim_warps=1,
        max_cycles=8,
        initial_registers={1: list(range(32)), 2: 10},
    )

    assert gpu.get_performance_counters()["total_cycles"] == 2
    assert gpu.sms[0].warps[0].rf[0][3] == 10
    assert gpu.sms[0].warps[0].rf[31][3] == 41


def test_simulator_executes_fp32_vector_subtraction():
    gpu = ZGPU(num_sms=1, global_mem_mb=1)
    program = Assembler.assemble("VFSUB R3, R1, R2\nHALT")
    gpu.launch_kernel(
        program,
        grid_dim=1,
        block_dim_warps=1,
        initial_registers={1: f32_to_bits(3.5), 2: f32_to_bits(1.25)},
    )
    assert bits_to_f32(gpu.sms[0].warps[0].rf[0][3]) == pytest.approx(2.25)


def test_simulator_rejects_unknown_opcode_during_execution():
    gpu = ZGPU(num_sms=1, global_mem_mb=1)
    with pytest.raises(ValueError, match="unknown zISA opcode"):
        gpu.launch_kernel([0x00000007], grid_dim=1, block_dim_warps=1, max_cycles=1)


def test_gpu_launch_stops_non_terminating_program_at_cycle_budget():
    gpu = ZGPU(num_sms=1, global_mem_mb=1)
    program = Assembler.assemble("LOOP:\nBRA LOOP")

    with pytest.raises(SimulationLimitError, match="3-cycle execution limit"):
        gpu.launch_kernel(program, grid_dim=1, block_dim_warps=1, max_cycles=3)

    assert gpu.get_performance_counters()["total_cycles"] == 3


def test_gpu_launch_rejects_invalid_resource_and_register_inputs():
    with pytest.raises(ValueError, match="num_sms"):
        ZGPU(num_sms=0)
    gpu = ZGPU(num_sms=1, global_mem_mb=1)
    program = Assembler.assemble("HALT")
    with pytest.raises(ValueError, match="warp capacity"):
        gpu.launch_kernel(program, grid_dim=1, block_dim_warps=9)
    with pytest.raises(ValueError, match="32 values"):
        gpu.launch_kernel(program, grid_dim=1, block_dim_warps=1, initial_registers={1: [1, 2]})


def test_shared_memory_bank_conflicts():
    shm = SharedMemory()
    # All 32 lanes access distinct banks: 0..31 -> 0 conflicts
    shm.access_warp(list(range(32)), 0xFFFFFFFF)
    assert shm.bank_conflicts == 0

    # All 32 lanes access same bank (index 0, 32, 64, ...) -> 31 conflicts
    conflicting_indices = [i * 32 for i in range(32)]
    shm.access_warp(conflicting_indices, 0xFFFFFFFF)
    assert shm.bank_conflicts == 31


def test_global_memory_rejects_negative_addresses_and_preserves_unsigned_words():
    memory = GlobalMemory(size_bytes=8)

    memory.write_i32(0, 0xFFFFFFFF)
    memory.write_i32(-4, 123)
    memory.write_f32(-4, 1.0)

    assert memory.read_i32(0) == -1
    assert memory.read_i32(-4) == 0
    assert memory.read_f32(-4) == 0.0
    assert memory.write_transactions == 1
    assert memory.read_transactions == 1


def test_global_memory_coalesced_warp_accesses_count_cache_lines_once():
    memory = GlobalMemory(size_bytes=512)
    addresses = [lane * 4 for lane in range(32)]
    values = [lane + 1 for lane in range(32)]
    for address, value in zip(addresses, values, strict=True):
        memory.write_i32(address, value)
    memory.write_transactions = 0

    loaded, read_lines = memory.coalesced_load_32(addresses, 0xFFFFFFFF)
    assert loaded == values
    assert read_lines == 1
    assert memory.read_transactions == 1

    written = memory.coalesced_store_32(addresses, [value * 2 for value in values], 0xFFFFFFFF)
    assert written == 1
    assert memory.write_transactions == 1
    assert memory.coalesced_load_32(addresses, 0xFFFFFFFF)[0] == [value * 2 for value in values]


def test_global_memory_coalesced_load_accounts_for_cache_line_crossing():
    memory = GlobalMemory(size_bytes=512)
    addresses = [124 + lane * 4 for lane in range(32)]
    for address in addresses:
        memory.write_i32(address, address)
    memory.read_transactions = 0

    values, transactions = memory.coalesced_load_32(addresses, 0xFFFFFFFF)

    assert values == addresses
    assert transactions == 2
    assert memory.read_transactions == 2
