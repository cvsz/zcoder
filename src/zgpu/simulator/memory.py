"""Memory Hierarchy Simulator: Coalesced Global Memory & Banked Shared Memory."""

from __future__ import annotations

import struct


class GlobalMemory:
    """Byte-addressable unified device DRAM (HBM/GDDR model)."""

    def __init__(self, size_bytes: int = 64 * 1024 * 1024):  # 64 MB
        self.size = size_bytes
        self.data = bytearray(size_bytes)
        self.read_transactions = 0
        self.write_transactions = 0

    def write_f32(self, addr: int, val: float):
        if addr >= 0 and addr + 4 <= self.size:
            struct.pack_into("<f", self.data, addr, val)
            self.write_transactions += 1

    def read_f32(self, addr: int) -> float:
        if addr >= 0 and addr + 4 <= self.size:
            self.read_transactions += 1
            return struct.unpack_from("<f", self.data, addr)[0]
        return 0.0

    def write_i32(self, addr: int, val: int):
        if addr >= 0 and addr + 4 <= self.size:
            value = int(val) & 0xFFFFFFFF
            if value >= 0x80000000:
                value -= 0x1_0000_0000
            struct.pack_into("<i", self.data, addr, value)
            self.write_transactions += 1

    def read_i32(self, addr: int) -> int:
        if addr >= 0 and addr + 4 <= self.size:
            self.read_transactions += 1
            return struct.unpack_from("<i", self.data, addr)[0]
        return 0

    def coalesced_load_32(self, addresses: list[int], active_mask: int) -> tuple[list[int], int]:
        """Simulate coalesced memory transaction logic for a 32-lane warp.
        Returns: (values, number_of_128B_cache_lines_requested)
        """
        lines = set()
        values = []
        for lane, addr in enumerate(addresses):
            if active_mask & (1 << lane):
                if addr >= 0 and addr + 4 <= self.size:
                    first_line = addr >> 7
                    last_line = (addr + 3) >> 7
                    lines.update(range(first_line, last_line + 1))
                    values.append(struct.unpack_from("<i", self.data, addr)[0])
                else:
                    values.append(0)
            else:
                values.append(0)
        self.read_transactions += len(lines)
        return values, len(lines)

    def coalesced_store_32(self, addresses: list[int], values: list[int], active_mask: int) -> int:
        """Store active lanes and count each touched 128-byte cache line once."""
        if len(addresses) != 32 or len(values) != 32:
            raise ValueError("coalesced warp stores require exactly 32 addresses and values")
        lines = set()
        for lane, (addr, value) in enumerate(zip(addresses, values, strict=True)):
            if active_mask & (1 << lane) and addr >= 0 and addr + 4 <= self.size:
                lines.update(range(addr >> 7, ((addr + 3) >> 7) + 1))
                signed_value = int(value) & 0xFFFFFFFF
                if signed_value >= 0x80000000:
                    signed_value -= 0x1_0000_0000
                struct.pack_into("<i", self.data, addr, signed_value)
        self.write_transactions += len(lines)
        return len(lines)


class SharedMemory:
    """32-banked on-chip scratchpad with bank conflict tracking."""

    NUM_BANKS = 32

    def __init__(self, size_bytes: int = 64 * 1024):  # 64 KB per SM
        self.size = size_bytes
        self.data = [0] * (size_bytes // 4)  # 32-bit words
        self.total_accesses = 0
        self.bank_conflicts = 0

    def access_warp(
        self,
        word_indices: list[int],
        active_mask: int,
        is_write: bool = False,
        write_vals: list[int] | None = None,
    ) -> list[int]:
        """Access shared memory across 32 lanes, tracking bank conflicts."""
        bank_usage: dict[int, list[int]] = {}
        results = [0] * 32

        for lane, word_idx in enumerate(word_indices):
            if active_mask & (1 << lane):
                bank = word_idx % self.NUM_BANKS
                bank_usage.setdefault(bank, []).append((lane, word_idx))

        # Check bank conflicts (multiple different word indices requesting same bank)
        for _bank, requests in bank_usage.items():
            unique_addrs = set(idx for _, idx in requests)
            if len(unique_addrs) > 1:
                self.bank_conflicts += len(unique_addrs) - 1

        for lane, word_idx in enumerate(word_indices):
            if active_mask & (1 << lane) and 0 <= word_idx < len(self.data):
                if is_write and write_vals is not None:
                    self.data[word_idx] = write_vals[lane]
                results[lane] = self.data[word_idx]

        self.total_accesses += 1
        return results
