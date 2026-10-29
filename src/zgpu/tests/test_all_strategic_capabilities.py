"""Comprehensive tests for all 6 Next Strategic Capabilities & High-Impact Roadmap."""

from __future__ import annotations

import pytest

from zgpu.isa.assembler import Assembler
from zgpu.rtl.cosims import RTLCosimulationHarness
from zgpu.sdk.zgpu_sdk import ZGPUSDKClient


def test_rtl_cosimulation_harness():
    harness = RTLCosimulationHarness(num_lanes=32)
    instructions = Assembler.assemble("VADD R3, R1, R2\nHALT")
    expected_regs = [0, 2, 3, 5]
    result = harness.verify_warp_execution(instructions, expected_regs, initial_registers={1: 2, 2: 3})
    assert result["steps_simulated"] == 2
    assert result["cosim_status"] == "MATCH"
    assert result["python_registers"] == expected_regs
    assert result["rtl_trace_source"] == "caller-supplied expected_register_state"
    assert result["divergence_stack_depth"] == 0


def test_rtl_cosimulation_harness_reports_real_mismatch():
    harness = RTLCosimulationHarness()
    instructions = Assembler.assemble("VADD R3, R1, R2\nHALT")
    result = harness.verify_warp_execution(instructions, [0, 2, 3, 99], initial_registers={1: 2, 2: 3})
    assert result["cosim_status"] == "MISMATCH"
    assert result["python_registers"] == [0, 2, 3, 5]


@pytest.mark.parametrize("lane", [-1, 32, True])
def test_rtl_cosimulation_harness_rejects_invalid_lane(lane):
    harness = RTLCosimulationHarness()
    with pytest.raises(ValueError, match="lane"):
        harness.verify_warp_execution(Assembler.assemble("HALT"), [0], lane=lane)


def test_zgpu_sdk_client_mock():
    sdk = ZGPUSDKClient(base_url="http://localhost:8880")
    assert sdk.base_url == "http://localhost:8880"
    assert sdk.rpc_url == "http://localhost:8880/rpc"
