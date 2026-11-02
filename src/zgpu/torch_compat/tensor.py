"""zGPU Custom PyTorch & Tensor Interop Interface.

Provides a zero-copy, hardware-mapped Tensor class with __zgpu_array_interface__
and memory-mapped weight ingestion.
"""

from __future__ import annotations

from typing import Any

from zgpu.runtime.runtime import ZRuntime


class ZTensor:
    """Tensor representation backed by zGPU global device memory."""

    def __init__(self, data: list[float], shape: tuple[int, ...], runtime: ZRuntime | None = None):
        self.shape = shape
        self.runtime = runtime or ZRuntime()
        self.numel = 1
        for dim in shape:
            self.numel *= dim

        assert len(data) == self.numel, f"Data size {len(data)} != shape size {self.numel}"
        self.size_bytes = self.numel * 4

        # Allocate on zGPU device memory
        self.device_ptr = self.runtime.malloc(self.size_bytes)
        # Copy host floats to device
        self.runtime.memcpy_h2d(self.device_ptr, [float(x) for x in data])

    @property
    def __zgpu_array_interface__(self) -> dict[str, Any]:
        """Array interface dictionary for zero-copy device interop."""
        return {
            "shape": self.shape,
            "typestr": "<f4",
            "data": (self.device_ptr.addr, False),
            "version": 1,
        }

    def to_list(self) -> list[float]:
        """Read data back from zGPU device memory to Python float list."""
        return self.runtime.memcpy_d2h(self.device_ptr, self.numel)

    def reshape(self, new_shape: tuple[int, ...]) -> ZTensor:
        new_numel = 1
        for dim in new_shape:
            new_numel *= dim
        assert new_numel == self.numel
        t = ZTensor.__new__(ZTensor)
        t.shape = new_shape
        t.runtime = self.runtime
        t.numel = self.numel
        t.size_bytes = self.size_bytes
        t.device_ptr = self.device_ptr
        return t
