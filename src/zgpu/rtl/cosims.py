"""Compare real Python SIMT execution against caller-supplied RTL register traces.

This module does not launch Verilator or prove RTL equivalence by itself.
"""

from __future__ import annotations

from typing import Any

from zgpu.simulator.gpu import ZGPU


class RTLCosimulationHarness:
    """Run zISA in the Python simulator and compare lane state with an RTL trace."""

    def __init__(self, num_lanes: int = 32):
        if isinstance(num_lanes, bool) or not isinstance(num_lanes, int) or num_lanes != 32:
            raise ValueError("zISA warp execution requires exactly 32 lanes")
        self.num_lanes = num_lanes
        self.gpu_sim = ZGPU(num_sms=1, global_mem_mb=1)

    def verify_warp_execution(
        self,
        instructions: list[int],
        expected_register_state: list[int],
        *,
        initial_registers: dict[int, int | list[int]] | None = None,
        max_cycles: int = 10_000,
        lane: int = 0,
    ) -> dict[str, Any]:
        """Execute instructions, then compare one lane with an externally captured RTL trace."""
        if not isinstance(instructions, list) or not instructions:
            raise ValueError("instructions must be a non-empty list of encoded zISA words")
        if not isinstance(expected_register_state, list) or not 1 <= len(expected_register_state) <= 128:
            raise ValueError("expected_register_state must contain 1 to 128 register values")
        if any(
            isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 0xFFFFFFFF
            for value in expected_register_state
        ):
            raise ValueError("expected register values must be unsigned 32-bit integers")
        if isinstance(lane, bool) or not isinstance(lane, int) or not 0 <= lane < self.num_lanes:
            raise ValueError("lane must be between 0 and 31")

        self.gpu_sim = ZGPU(num_sms=1, global_mem_mb=1)
        self.gpu_sim.launch_kernel(
            instructions,
            grid_dim=1,
            block_dim_warps=1,
            max_cycles=max_cycles,
            initial_registers=initial_registers,
        )
        warp = self.gpu_sim.sms[0].warps[0]
        python_registers = list(warp.rf[lane][: len(expected_register_state)])
        match = python_registers == expected_register_state
        return {
            "cosim_status": "MATCH" if match else "MISMATCH",
            "execution": "python-simulator",
            "rtl_trace_source": "caller-supplied expected_register_state",
            "steps_simulated": self.gpu_sim.total_cycles,
            "instructions_submitted": len(instructions),
            "python_registers": python_registers,
            "rtl_expected": list(expected_register_state),
            "divergence_stack_depth": len(warp.divergence_stack),
            "performance_counters": self.gpu_sim.get_performance_counters(),
        }
