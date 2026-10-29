"""Bounded zISA assembly helpers for the local zGPU workspace."""

from __future__ import annotations

import math
import re

from zgpu.compiler.ast_compiler import AstJitCompiler
from zgpu.isa.assembler import OPCODE_MAP, Assembler
from zgpu.simulator.gpu import ZGPU, SimulationLimitError

MAX_SOURCE_CHARS = 65_536
MAX_INSTRUCTIONS = 4_096


class ZISAAssemblyError(ValueError):
    """Assembly input is invalid or outside the local studio limits."""

    def __init__(self, message: str, status: int = 400):
        self.status = status
        super().__init__(message)


class ZISASimulationError(ValueError):
    """Simulation input is invalid or execution exceeded its bounded budget."""

    def __init__(self, message: str, status: int = 400):
        self.status = status
        super().__init__(message)


def list_opcodes() -> list[dict[str, int | str]]:
    """Return canonical assembler mnemonics and established opcode values."""
    return [{"mnemonic": name, "opcode": int(opcode)} for name, opcode in OPCODE_MAP.items()]


def assemble_source(source: str) -> dict[str, object]:
    """Assemble bounded source with the repository's existing 32-bit ISA codec."""
    if not isinstance(source, str):
        raise ZISAAssemblyError("source must be a string")
    if len(source) > MAX_SOURCE_CHARS:
        raise ZISAAssemblyError(f"source must be at most {MAX_SOURCE_CHARS} characters", status=413)
    if not source.strip():
        raise ZISAAssemblyError("source must contain at least one instruction")

    try:
        words = Assembler.assemble(source)
    except (IndexError, TypeError, ValueError) as exc:
        raise ZISAAssemblyError(f"assembly failed: {exc}") from exc

    if not words:
        raise ZISAAssemblyError("source must contain at least one instruction")
    if len(words) > MAX_INSTRUCTIONS:
        raise ZISAAssemblyError(f"program must contain at most {MAX_INSTRUCTIONS} instructions", status=413)
    if any(not isinstance(word, int) or not 0 <= word <= 0xFFFFFFFF for word in words):
        raise ZISAAssemblyError("assembler returned a word outside the 32-bit instruction range")

    return {
        "target": "zISA-32",
        "execution": "not-run",
        "instruction_count": len(words),
        "byte_count": len(words) * 4,
        "word_hex": [f"0x{word:08X}" for word in words],
        "bytecode_le_hex": [word.to_bytes(4, byteorder="little").hex() for word in words],
    }


def simulate_elementwise_expression(
    expression: str,
    a_values: list[int | float],
    b_values: list[int | float],
    *,
    max_cycles: int = 10_000,
) -> dict[str, object]:
    """Compile and run one 32-element FP32 expression on the software SIMT simulator."""
    if (
        not isinstance(a_values, list)
        or not isinstance(b_values, list)
        or len(a_values) != 32
        or len(b_values) != 32
    ):
        raise ZISASimulationError("a and b must each contain exactly 32 numeric values")
    normalized_vectors = []
    for values in (a_values, b_values):
        normalized = []
        for value in values:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ZISASimulationError("a and b values must be finite FP32-range numbers")
            try:
                converted = float(value)
            except (OverflowError, ValueError) as exc:
                raise ZISASimulationError("a and b values must be finite FP32-range numbers") from exc
            if not math.isfinite(converted) or abs(converted) > 3.402823466e38:
                raise ZISASimulationError("a and b values must be finite FP32-range numbers")
            normalized.append(converted)
        normalized_vectors.append(normalized)
    a_values, b_values = normalized_vectors
    if isinstance(max_cycles, bool) or not isinstance(max_cycles, int) or not 1 <= max_cycles <= 20_000:
        raise ZISASimulationError("max_cycles must be between 1 and 20000")
    try:
        source = AstJitCompiler.compile_expression(expression)
        words = Assembler.assemble(source)
    except (ValueError, TypeError) as exc:
        raise ZISAAssemblyError(str(exc)) from exc

    gpu = ZGPU(num_sms=1, global_mem_mb=1)
    a_base, b_base, output_base = 0, 128, 256
    try:
        for index, value in enumerate(a_values):
            gpu.global_mem.write_f32(a_base + index * 4, value)
        for index, value in enumerate(b_values):
            gpu.global_mem.write_f32(b_base + index * 4, value)
        gpu.launch_kernel(
            words,
            grid_dim=1,
            block_dim_warps=1,
            max_cycles=max_cycles,
            initial_registers={1: 4, 2: output_base, 3: a_base, 4: b_base},
        )
        result = [gpu.global_mem.read_f32(output_base + index * 4) for index in range(32)]
        if any(not math.isfinite(value) for value in result):
            raise ZISASimulationError("expression produced a non-finite FP32 result", status=422)
    except SimulationLimitError as exc:
        raise ZISASimulationError(str(exc), status=408) from exc
    except ZISASimulationError:
        raise
    except OverflowError as exc:
        raise ZISASimulationError("expression produced an out-of-range FP32 result", status=422) from exc
    except ValueError as exc:
        raise ZISASimulationError("simulator rejected the generated kernel") from exc

    return {
        "target": "zGPU-SIMT-Simulator",
        "execution": "simulated",
        "compiler": "zGPU restricted Python AST compiler",
        "expression": expression,
        "warp_width": 32,
        "instruction_count": len(words),
        "result": result,
        "performance_counters": gpu.get_performance_counters(),
    }


def simulate_source(
    source: str,
    *,
    inputs: dict[str, int | list[int]] | None = None,
    output_registers: list[int] | None = None,
    max_cycles: int = 10_000,
) -> dict[str, object]:
    """Run one bounded 32-lane warp on the canonical zGPU software simulator."""
    if isinstance(max_cycles, bool) or not isinstance(max_cycles, int) or not 1 <= max_cycles <= 20_000:
        raise ZISASimulationError("max_cycles must be between 1 and 20000")
    assembled = assemble_source(source)
    words = [int(word, 16) for word in assembled["word_hex"]]

    if inputs is None:
        inputs = {}
    if not isinstance(inputs, dict) or len(inputs) > 16:
        raise ZISASimulationError("inputs must be an object with at most 16 registers")
    initial_registers: dict[int, int | list[int]] = {}
    for key, values in inputs.items():
        match = re.fullmatch(r"R?([0-9]{1,3})", key, flags=re.IGNORECASE) if isinstance(key, str) else None
        if match is None:
            raise ZISASimulationError("input register keys must use R0-R127 or 0-127")
        register = int(match.group(1))
        if register > 127 or register in initial_registers:
            raise ZISASimulationError("input register keys must be unique values from R0 to R127")
        if isinstance(values, list):
            if len(values) != 32:
                raise ZISASimulationError("per-lane inputs must contain exactly 32 values")
            if any(
                isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 0xFFFFFFFF
                for value in values
            ):
                raise ZISASimulationError("input values must be unsigned 32-bit integers")
        elif isinstance(values, bool) or not isinstance(values, int) or not 0 <= values <= 0xFFFFFFFF:
            raise ZISASimulationError("input values must be unsigned 32-bit integers")
        initial_registers[register] = values

    if output_registers is None:
        output_registers = [0, 1, 2, 3]
    if (
        not isinstance(output_registers, list)
        or not 1 <= len(output_registers) <= 8
        or any(
            isinstance(register, bool) or not isinstance(register, int) or not 0 <= register <= 127
            for register in output_registers
        )
        or len(set(output_registers)) != len(output_registers)
    ):
        raise ZISASimulationError(
            "output_registers must contain 1 to 8 unique register numbers from 0 to 127"
        )

    gpu = ZGPU(num_sms=1, global_mem_mb=1)
    try:
        gpu.launch_kernel(
            words,
            grid_dim=1,
            block_dim_warps=1,
            max_cycles=max_cycles,
            initial_registers=initial_registers,
        )
    except SimulationLimitError as exc:
        raise ZISASimulationError(str(exc), status=408) from exc
    except ValueError as exc:
        raise ZISASimulationError("simulator rejected the assembled program") from exc
    except Exception as exc:
        raise ZISASimulationError("simulator could not execute this program", status=422) from exc

    warp = gpu.sms[0].warps[0]
    outputs = {f"R{register}": [lane[register] for lane in warp.rf] for register in output_registers}
    return {
        "target": "zGPU-SIMT-Simulator",
        "execution": "simulated",
        "warp_width": 32,
        "instruction_count": len(words),
        "performance_counters": gpu.get_performance_counters(),
        "registers": outputs,
    }
