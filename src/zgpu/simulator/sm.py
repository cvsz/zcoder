"""zGPU Streaming Multiprocessor (SM) Core Simulator."""

from __future__ import annotations

import struct

from zgpu.isa.instructions import Instruction, Opcode
from zgpu.simulator.memory import GlobalMemory, SharedMemory
from zgpu.simulator.warp import WARP_SIZE, Warp


def f32_to_bits(f: float) -> int:
    return struct.unpack("<I", struct.pack("<f", f))[0]


def bits_to_f32(b: int) -> float:
    return struct.unpack("<f", struct.pack("<I", b & 0xFFFFFFFF))[0]


class StreamingMultiprocessor:
    """SM execution core running multiple Warps with SIMT schedule & execution units."""

    def __init__(self, sm_id: int, global_mem: GlobalMemory, max_warps: int = 8):
        self.sm_id = sm_id
        self.global_mem = global_mem
        self.shared_mem = SharedMemory()
        self.warps: list[Warp] = []
        self.max_warps = max_warps
        self.active_warp_idx = 0
        self.cycle_count = 0
        self.instructions_retired = 0

    def launch_warps(self, num_warps: int, block_id: int = 0):
        self.warps = [Warp(w_id, block_id) for w_id in range(num_warps)]

    def is_finished(self) -> bool:
        return all(w.halted for w in self.warps)

    def step_cycle(self, program: list[int]) -> bool:
        """Cycle-accurate SM tick with Greedy-Then-Oldest (GTO) warp scheduler."""
        if self.is_finished() or not self.warps:
            return False

        self.cycle_count += 1

        # GTO Warp Scheduling: find first ready non-halted warp
        selected_warp: Warp | None = None
        for i in range(len(self.warps)):
            idx = (self.active_warp_idx + i) % len(self.warps)
            if not self.warps[idx].halted and not self.warps[idx].stalled:
                selected_warp = self.warps[idx]
                self.active_warp_idx = (idx + 1) % len(self.warps)
                break

        if not selected_warp:
            return True

        if selected_warp.pc >= len(program):
            selected_warp.halted = True
            return True

        # Fetch and decode
        inst_word = program[selected_warp.pc]
        inst = Instruction.decode(inst_word)
        selected_warp.pc += 1

        # Execute instruction across 32 lanes
        self._execute_instruction(selected_warp, inst)
        selected_warp.cycles_executed += 1
        self.instructions_retired += 1
        return True

    def _execute_instruction(self, warp: Warp, inst: Instruction):
        op = inst.op

        if op == Opcode.NOP:
            return

        elif op == Opcode.HALT:
            warp.halted = True
            return

        elif op == Opcode.GET_TID:
            for lane in range(WARP_SIZE):
                if warp.is_active(lane):
                    warp.rf[lane][inst.rd] = lane + warp.warp_id * WARP_SIZE

        elif op == Opcode.GET_BID:
            for lane in range(WARP_SIZE):
                if warp.is_active(lane):
                    warp.rf[lane][inst.rd] = warp.block_id

        # Integer Arithmetic
        elif op == Opcode.VADD:
            for lane in range(WARP_SIZE):
                if warp.is_active(lane):
                    v1 = warp.rf[lane][inst.rs1]
                    v2 = warp.rf[lane][inst.rs2]
                    warp.rf[lane][inst.rd] = (v1 + v2) & 0xFFFFFFFF

        elif op == Opcode.VSUB:
            for lane in range(WARP_SIZE):
                if warp.is_active(lane):
                    v1 = warp.rf[lane][inst.rs1]
                    v2 = warp.rf[lane][inst.rs2]
                    warp.rf[lane][inst.rd] = (v1 - v2) & 0xFFFFFFFF

        elif op == Opcode.VMUL:
            for lane in range(WARP_SIZE):
                if warp.is_active(lane):
                    v1 = warp.rf[lane][inst.rs1]
                    v2 = warp.rf[lane][inst.rs2]
                    warp.rf[lane][inst.rd] = (v1 * v2) & 0xFFFFFFFF

        # Floating Point Operations
        elif op == Opcode.VFADD:
            for lane in range(WARP_SIZE):
                if warp.is_active(lane):
                    f1 = bits_to_f32(warp.rf[lane][inst.rs1])
                    f2 = bits_to_f32(warp.rf[lane][inst.rs2])
                    warp.rf[lane][inst.rd] = f32_to_bits(f1 + f2)

        elif op == Opcode.VFSUB:
            for lane in range(WARP_SIZE):
                if warp.is_active(lane):
                    f1 = bits_to_f32(warp.rf[lane][inst.rs1])
                    f2 = bits_to_f32(warp.rf[lane][inst.rs2])
                    warp.rf[lane][inst.rd] = f32_to_bits(f1 - f2)

        elif op == Opcode.VFMUL:
            for lane in range(WARP_SIZE):
                if warp.is_active(lane):
                    f1 = bits_to_f32(warp.rf[lane][inst.rs1])
                    f2 = bits_to_f32(warp.rf[lane][inst.rs2])
                    warp.rf[lane][inst.rd] = f32_to_bits(f1 * f2)

        elif op == Opcode.VFFMA:
            for lane in range(WARP_SIZE):
                if warp.is_active(lane):
                    f1 = bits_to_f32(warp.rf[lane][inst.rs1])
                    f2 = bits_to_f32(warp.rf[lane][inst.rs2])
                    f3 = bits_to_f32(warp.rf[lane][inst.rs3])
                    warp.rf[lane][inst.rd] = f32_to_bits(f1 * f2 + f3)

        # Global Memory
        elif op == Opcode.VLOAD_G:
            addrs = [warp.rf[lane][inst.rs1] + inst.imm for lane in range(WARP_SIZE)]
            vals, _lines = self.global_mem.coalesced_load_32(addrs, warp.active_mask)
            for lane in range(WARP_SIZE):
                if warp.is_active(lane):
                    warp.rf[lane][inst.rd] = vals[lane]

        elif op == Opcode.VSTORE_G:
            addrs = [warp.rf[lane][inst.rs1] + inst.imm for lane in range(WARP_SIZE)]
            values = [warp.rf[lane][inst.rs2] for lane in range(WARP_SIZE)]
            self.global_mem.coalesced_store_32(addrs, values, warp.active_mask)

        # Shared Memory
        elif op == Opcode.VLOAD_S:
            indices = [(warp.rf[lane][inst.rs1] + inst.imm) >> 2 for lane in range(WARP_SIZE)]
            vals = self.shared_mem.access_warp(indices, warp.active_mask, is_write=False)
            for lane in range(WARP_SIZE):
                if warp.is_active(lane):
                    warp.rf[lane][inst.rd] = vals[lane]

        elif op == Opcode.VSTORE_S:
            indices = [(warp.rf[lane][inst.rs1] + inst.imm) >> 2 for lane in range(WARP_SIZE)]
            vals = [warp.rf[lane][inst.rs2] for lane in range(WARP_SIZE)]
            self.shared_mem.access_warp(indices, warp.active_mask, is_write=True, write_vals=vals)

        # Branching and Divergence
        elif op == Opcode.BRA:
            warp.pc = warp.pc - 1 + inst.imm

        elif op == Opcode.BRA_DIV:
            taken_mask = 0
            for lane in range(WARP_SIZE):
                if warp.is_active(lane) and warp.rf[lane][inst.rs1] != 0:
                    taken_mask |= 1 << lane

            target_pc = warp.pc - 1 + inst.imm
            fallthrough_pc = warp.pc
            warp.split_divergence(fallthrough_pc=fallthrough_pc, branch_pc=target_pc, taken_mask=taken_mask)

        elif op == Opcode.JOIN:
            warp.pop_divergence()

        # Tensor MMA Acceleration (4x4 Matrix Multiply Tile)
        elif op == Opcode.MMA_SYNC:
            # 16 lanes participate to compute 4x4 matrix product
            for r in range(4):
                for c in range(4):
                    lane = r * 4 + c
                    if warp.is_active(lane):
                        acc = bits_to_f32(warp.rf[lane][inst.rs3])
                        for k in range(4):
                            a_val = bits_to_f32(warp.rf[r * 4 + k][inst.rs1])
                            b_val = bits_to_f32(warp.rf[k * 4 + c][inst.rs2])
                            acc += a_val * b_val
                        warp.rf[lane][inst.rd] = f32_to_bits(acc)
