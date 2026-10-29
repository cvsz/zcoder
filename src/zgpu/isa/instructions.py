"""zGPU Instruction Set Architecture definitions and binary codec."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class Opcode(IntEnum):
    NOP = 0x00
    # Vector Arithmetic Integer
    VADD = 0x01
    VSUB = 0x02
    VMUL = 0x03
    VAND = 0x04
    VOR = 0x05
    VXOR = 0x06
    # Vector Arithmetic Float
    VFADD = 0x10
    VFSUB = 0x11
    VFMUL = 0x12
    VFFMA = 0x13
    # Memory Loads/Stores
    VLOAD_G = 0x20  # Vector Load Global
    VSTORE_G = 0x21  # Vector Store Global
    VLOAD_S = 0x22  # Vector Load Shared
    VSTORE_S = 0x23  # Vector Store Shared
    # Flow & Warp Divergence
    BRA = 0x30
    BRA_DIV = 0x31  # Branch on vector condition (divergence push)
    JOIN = 0x32  # Reconvergence pop
    BAR_SYNC = 0x33  # Thread block barrier
    # Tensor / Matrix Acceleration
    MMA_SYNC = 0x40  # 4x4 matrix multiply-accumulate
    # Special Registers & IDs
    GET_TID = 0x50  # Get thread lane ID
    GET_BID = 0x51  # Get block ID
    # Termination
    HALT = 0x7F


@dataclass(frozen=True)
class Instruction:
    op: Opcode
    rd: int = 0
    rs1: int = 0
    rs2: int = 0
    rs3: int = 0
    imm: int = 0
    comment: str = ""

    def encode(self) -> int:
        """Encode 32-bit binary instruction word."""
        if not isinstance(self.op, Opcode):
            raise ValueError("op must be a valid zISA opcode")
        if not isinstance(self.rd, int) or isinstance(self.rd, bool) or not 0 <= self.rd <= 0x7F:
            raise ValueError("rd must fit the 7-bit destination field (0..127)")
        for name, value in (("rs1", self.rs1), ("rs2", self.rs2), ("rs3", self.rs3)):
            if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 0x1F:
                raise ValueError(f"{name} must fit a 5-bit register field (0..31)")
        if not isinstance(self.imm, int) or isinstance(self.imm, bool) or not -128 <= self.imm <= 127:
            raise ValueError("imm must fit the signed 8-bit field (-128..127)")
        # [31:24] imm/rs3, [23:19] rs2, [18:14] rs1, [13:7] rd, [6:0] opcode
        raw = self.op & 0x7F
        raw |= (self.rd & 0x7F) << 7
        raw |= (self.rs1 & 0x1F) << 14
        raw |= (self.rs2 & 0x1F) << 19
        if self.op == Opcode.MMA_SYNC:
            raw |= (self.rs3 & 0x1F) << 24
        else:
            raw |= (self.imm & 0xFF) << 24
        return raw & 0xFFFFFFFF

    @classmethod
    def decode(cls, word: int) -> Instruction:
        """Decode 32-bit instruction word."""
        if isinstance(word, bool) or not isinstance(word, int) or not 0 <= word <= 0xFFFFFFFF:
            raise ValueError("instruction word must be an unsigned 32-bit integer")
        op_val = word & 0x7F
        try:
            op = Opcode(op_val)
        except ValueError as exc:
            raise ValueError(f"unknown zISA opcode 0x{op_val:02X}") from exc
        rd = (word >> 7) & 0x7F
        rs1 = (word >> 14) & 0x1F
        rs2 = (word >> 19) & 0x1F
        imm = (word >> 24) & 0xFF
        # Sign-extend 8-bit immediate if negative
        if imm & 0x80:
            imm -= 0x100
        rs3 = (word >> 24) & 0x1F
        return cls(op=op, rd=rd, rs1=rs1, rs2=rs2, rs3=rs3, imm=imm)
