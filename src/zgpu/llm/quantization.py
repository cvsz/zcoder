"""zGPU INT8 & INT4 Quantization Engine.

Provides high-performance symmetric and asymmetric tensor quantization to maximize
memory bandwidth efficiency and compute density on zGPU hardware.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class QuantizedTensor:
    q_data: list[int]
    scale: float
    zero_point: int
    shape: tuple[int, ...]
    bits: int = 8

    def dequantize(self) -> list[float]:
        """Convert quantized integers back to FP32."""
        return [(val - self.zero_point) * self.scale for val in self.q_data]


class Quantizer:
    """Hardware-friendly INT8 / INT4 Quantization routines."""

    @staticmethod
    def quantize_int8_symmetric(data: list[float], shape: tuple[int, ...]) -> QuantizedTensor:
        """Quantize FP32 to signed 8-bit integers [-127, 127] with zero_point = 0."""
        max_abs = max(abs(x) for x in data) if data else 1e-8
        scale = max_abs / 127.0 if max_abs > 0 else 1.0

        q_data = []
        for val in data:
            q_val = round(val / scale)
            q_val = max(-127, min(127, q_val))
            q_data.append(q_val)

        return QuantizedTensor(q_data=q_data, scale=scale, zero_point=0, shape=shape, bits=8)

    @staticmethod
    def quantize_int4_symmetric(data: list[float], shape: tuple[int, ...]) -> QuantizedTensor:
        """Quantize FP32 to signed 4-bit integers [-7, 7] with zero_point = 0."""
        max_abs = max(abs(x) for x in data) if data else 1e-8
        scale = max_abs / 7.0 if max_abs > 0 else 1.0

        q_data = []
        for val in data:
            q_val = round(val / scale)
            q_val = max(-7, min(7, q_val))
            q_data.append(q_val)

        return QuantizedTensor(q_data=q_data, scale=scale, zero_point=0, shape=shape, bits=4)

    @staticmethod
    def pack_int4(int4_vals: list[int]) -> list[int]:
        """Pack two 4-bit signed integers into a single 8-bit byte."""
        packed = []
        for i in range(0, len(int4_vals), 2):
            v0 = int4_vals[i] & 0x0F
            v1 = (int4_vals[i + 1] & 0x0F) if i + 1 < len(int4_vals) else 0
            packed.append((v1 << 4) | v0)
        return packed

    @staticmethod
    def unpack_int4(packed: list[int], target_len: int) -> list[int]:
        """Unpack 8-bit bytes into 4-bit signed integers."""
        unpacked = []
        for byte in packed:
            v0 = byte & 0x0F
            if v0 >= 8:
                v0 -= 16  # sign extension
            unpacked.append(v0)
            if len(unpacked) >= target_len:
                break

            v1 = (byte >> 4) & 0x0F
            if v1 >= 8:
                v1 -= 16  # sign extension
            unpacked.append(v1)
            if len(unpacked) >= target_len:
                break
        return unpacked
