"""zGPU Autonomous Kernel Benchmarking, Verification and Mutation Evaluator."""

from __future__ import annotations

from dataclasses import dataclass

from zgpu.isa.assembler import Assembler
from zgpu.runtime.runtime import ZRuntime
from zgpu.self_coding.generator import GeneratedKernel


@dataclass
class EvaluationReport:
    kernel_name: str
    valid: bool
    cycles_elapsed: int
    instructions_retired: int
    ipc: float
    error_message: str | None = None


class KernelEvaluator:
    """Simulates and profiles self-coded kernels on cycle-accurate zGPU hardware."""

    def __init__(self, runtime: ZRuntime | None = None):
        self.runtime = runtime or ZRuntime()

    def evaluate_kernel(self, kernel: GeneratedKernel, num_warps: int = 1) -> EvaluationReport:
        if not kernel.bytecode:
            try:
                kernel.bytecode = Assembler.assemble(kernel.source_code)
            except Exception as e:
                return EvaluationReport(
                    kernel_name=kernel.name,
                    valid=False,
                    cycles_elapsed=0,
                    instructions_retired=0,
                    ipc=0.0,
                    error_message=f"Assembly failed: {e}",
                )

        sm = self.runtime.device.sms[0]
        sm.launch_warps(num_warps)

        cycles = 0
        max_cycles = 10000

        try:
            while not sm.is_finished() and cycles < max_cycles:
                sm.step_cycle(kernel.bytecode)
                cycles += 1

            retired = sm.instructions_retired
            ipc = (retired / cycles) if cycles > 0 else 0.0

            return EvaluationReport(
                kernel_name=kernel.name,
                valid=sm.is_finished(),
                cycles_elapsed=cycles,
                instructions_retired=retired,
                ipc=ipc,
                error_message=None if sm.is_finished() else "Timeout / deadlock detected",
            )
        except Exception as e:
            return EvaluationReport(
                kernel_name=kernel.name,
                valid=False,
                cycles_elapsed=cycles,
                instructions_retired=0,
                ipc=0.0,
                error_message=str(e),
            )
