"""zGPU Host Runtime API (Driver abstraction modeled after CUDA / OpenCL)."""

from __future__ import annotations

from zgpu.isa.assembler import Assembler
from zgpu.simulator.gpu import ZGPU


class DevicePointer:
    def __init__(self, addr: int, size: int):
        self.addr = addr
        self.size = size


class ZRuntime:
    """Device driver and memory allocator runtime for zGPU."""

    def __init__(self, num_sms: int = 4):
        self.device = ZGPU(num_sms=num_sms)
        self.heap_head = 0x1000  # Start heap after interrupt vector table

    def malloc(self, size_bytes: int) -> DevicePointer:
        """Allocate aligned device global memory."""
        # Align to 128 bytes (L2 cache line boundary)
        aligned = (self.heap_head + 127) & ~127
        self.heap_head = aligned + size_bytes
        if self.heap_head > self.device.global_mem.size:
            raise MemoryError("zGPU Out of Memory (OOM)")
        return DevicePointer(aligned, size_bytes)

    def memcpy_h2d(self, dst: DevicePointer, src_data: list[float]):
        """Copy host array to device memory (FP32)."""
        for i, val in enumerate(src_data):
            self.device.global_mem.write_f32(dst.addr + i * 4, float(val))

    def memcpy_d2h(self, src: DevicePointer, num_floats: int) -> list[float]:
        """Copy device memory back to host array (FP32)."""
        return [self.device.global_mem.read_f32(src.addr + i * 4) for i in range(num_floats)]

    def launch(self, kernel_source: str, grid_dim: int = 1, block_dim_warps: int = 1):
        """Assemble and launch an asynchronous grid across zGPU compute clusters."""
        bytecode = Assembler.assemble(kernel_source)
        self.device.launch_kernel(bytecode, grid_dim=grid_dim, block_dim_warps=block_dim_warps)

    def synchronize(self):
        """Block until all compute clusters reach HALT."""
        pass  # In simulator, kernel launch synchronously finishes execution
