"""zGPU Warp Microarchitecture and SIMT Execution Model."""

from __future__ import annotations

from dataclasses import dataclass

WARP_SIZE = 32


@dataclass
class DivergenceStackEntry:
    target_pc: int
    active_mask: int


class Warp:
    """Represents a SIMT Warp executing in lockstep with 32 lanes."""

    def __init__(self, warp_id: int, block_id: int, num_regs: int = 128):
        self.warp_id = warp_id
        self.block_id = block_id
        self.pc = 0
        self.active_mask = 0xFFFFFFFF  # All 32 lanes active initially
        self.divergence_stack: list[DivergenceStackEntry] = []
        # Register file: 32 lanes x num_regs (32-bit registers)
        self.rf: list[list[int]] = [[0] * num_regs for _ in range(WARP_SIZE)]
        self.halted = False
        self.stalled = False
        self.cycles_executed = 0

        # Initialize thread IDs (R0 = tid_in_warp + warp_id * 32)
        for lane in range(WARP_SIZE):
            self.rf[lane][0] = lane + self.warp_id * WARP_SIZE
            self.rf[lane][1] = self.block_id

    def is_active(self, lane: int) -> bool:
        return bool(self.active_mask & (1 << lane))

    def split_divergence(self, fallthrough_pc: int, branch_pc: int, taken_mask: int):
        """Standard IP-divergence stack for SIMT architectures."""
        orig_mask = self.active_mask
        taken_active = orig_mask & taken_mask
        fallthrough_active = orig_mask & (~taken_mask)

        # If both paths have active lanes, push the fallthrough path to be run later
        if taken_active and fallthrough_active:
            # When taken finishes and hits JOIN, it pops fallthrough
            self.divergence_stack.append(
                DivergenceStackEntry(target_pc=fallthrough_pc, active_mask=fallthrough_active)
            )
            self.active_mask = taken_active
            self.pc = branch_pc
        elif taken_active:
            self.pc = branch_pc
        else:
            self.pc = fallthrough_pc

    def pop_divergence(self) -> bool:
        """Handle JOIN / reconvergence."""
        if self.divergence_stack:
            entry = self.divergence_stack.pop()
            self.pc = entry.target_pc
            self.active_mask = entry.active_mask
            return True
        return False
