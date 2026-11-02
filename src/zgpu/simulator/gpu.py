"""zGPU Top-Level Multi-SM Hardware Prototype & Device Orchestrator."""

from __future__ import annotations

from typing import Any

from zgpu.simulator.memory import GlobalMemory
from zgpu.simulator.sm import StreamingMultiprocessor


class SimulationLimitError(RuntimeError):
    """Raised when a bounded kernel launch exceeds its cycle budget."""


class ZGPU:
    """Complete zGPU hardware prototype with scalable SM cluster configuration."""

    def __init__(self, num_sms: int = 4, global_mem_mb: int = 64):
        if isinstance(num_sms, bool) or not isinstance(num_sms, int) or num_sms < 1:
            raise ValueError("num_sms must be a positive integer")
        if isinstance(global_mem_mb, bool) or not isinstance(global_mem_mb, int) or global_mem_mb < 1:
            raise ValueError("global_mem_mb must be a positive integer")
        self.num_sms = num_sms
        self.global_mem = GlobalMemory(global_mem_mb * 1024 * 1024)
        self.sms = [StreamingMultiprocessor(sm_id=i, global_mem=self.global_mem) for i in range(num_sms)]
        self.total_cycles = 0

    def launch_kernel(
        self,
        program: list[int],
        grid_dim: int,
        block_dim_warps: int,
        *,
        max_cycles: int | None = None,
        initial_registers: dict[int, int | list[int]] | None = None,
    ):
        """Dispatch a grid of thread blocks across available SMs."""
        if max_cycles is not None and (
            isinstance(max_cycles, bool) or not isinstance(max_cycles, int) or max_cycles < 1
        ):
            raise ValueError("max_cycles must be a positive integer")
        if isinstance(grid_dim, bool) or not isinstance(grid_dim, int) or grid_dim < 1:
            raise ValueError("grid_dim must be a positive integer")
        if isinstance(block_dim_warps, bool) or not isinstance(block_dim_warps, int) or block_dim_warps < 1:
            raise ValueError("block_dim_warps must be a positive integer")
        if any(block_dim_warps > sm.max_warps for sm in self.sms):
            raise ValueError("block_dim_warps cannot exceed the SM warp capacity")
        if initial_registers is None:
            initial_registers = {}
        if not isinstance(initial_registers, dict):
            raise ValueError("initial_registers must be a register mapping")
        for register, values in initial_registers.items():
            if isinstance(register, bool) or not isinstance(register, int) or not 0 <= register < 128:
                raise ValueError("initial register index must be between 0 and 127")
            if isinstance(values, list):
                if len(values) != 32:
                    raise ValueError("per-lane register input must contain exactly 32 values")
                register_values = values
            else:
                register_values = [values] * 32
            if any(
                isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 0xFFFFFFFF
                for value in register_values
            ):
                raise ValueError("register values must be unsigned 32-bit integers")

        # Distribute blocks round-robin to SMs
        block_queue = list(range(grid_dim))
        starting_cycles = self.total_cycles

        while block_queue or any(not sm.is_finished() for sm in self.sms):
            if max_cycles is not None and self.total_cycles - starting_cycles >= max_cycles:
                raise SimulationLimitError(f"kernel exceeded its {max_cycles}-cycle execution limit")
            for sm in self.sms:
                if sm.is_finished() and block_queue:
                    bid = block_queue.pop(0)
                    sm.launch_warps(num_warps=block_dim_warps, block_id=bid)
                    for warp in sm.warps:
                        for register, values in initial_registers.items():
                            register_values = values if isinstance(values, list) else [values] * 32
                            for lane, value in enumerate(register_values):
                                warp.rf[lane][register] = value

            # Cycle tick all SMs concurrently
            any_active = False
            for sm in self.sms:
                if not sm.is_finished():
                    sm.step_cycle(program)
                    any_active = True

            if any_active:
                self.total_cycles += 1

    def get_performance_counters(self) -> dict[str, Any]:
        total_instructions = sum(sm.instructions_retired for sm in self.sms)
        total_conflicts = sum(sm.shared_mem.bank_conflicts for sm in self.sms)
        ipc = total_instructions / max(1, self.total_cycles)

        return {
            "total_cycles": self.total_cycles,
            "total_instructions": total_instructions,
            "ipc": round(ipc, 2),
            "dram_reads": self.global_mem.read_transactions,
            "dram_writes": self.global_mem.write_transactions,
            "shared_mem_bank_conflicts": total_conflicts,
        }
