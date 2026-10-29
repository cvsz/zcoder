"""zGPU Assembler: converts human-readable SIMT assembly to binary bytecode."""

from __future__ import annotations

import re

from zgpu.isa.instructions import Instruction, Opcode

OPCODE_MAP = {
    "NOP": Opcode.NOP,
    "VADD": Opcode.VADD,
    "VSUB": Opcode.VSUB,
    "VMUL": Opcode.VMUL,
    "VAND": Opcode.VAND,
    "VOR": Opcode.VOR,
    "VXOR": Opcode.VXOR,
    "VFADD": Opcode.VFADD,
    "VFSUB": Opcode.VFSUB,
    "VFMUL": Opcode.VFMUL,
    "VFFMA": Opcode.VFFMA,
    "VLOAD.G": Opcode.VLOAD_G,
    "VSTORE.G": Opcode.VSTORE_G,
    "VLOAD.S": Opcode.VLOAD_S,
    "VSTORE.S": Opcode.VSTORE_S,
    "BRA": Opcode.BRA,
    "BRA.DIV": Opcode.BRA_DIV,
    "JOIN": Opcode.JOIN,
    "BAR.SYNC": Opcode.BAR_SYNC,
    "MMA.SYNC": Opcode.MMA_SYNC,
    "GET.TID": Opcode.GET_TID,
    "GET.BID": Opcode.GET_BID,
    "HALT": Opcode.HALT,
}


def parse_reg(token: str) -> int:
    token = token.strip().upper()
    if token.startswith("R"):
        return int(token[1:])
    raise ValueError(f"Invalid register name: {token}")


class Assembler:
    @staticmethod
    def assemble(source: str) -> list[int]:
        labels: dict[str, int] = {}
        lines = source.strip().splitlines()
        clean_lines = []

        # Pass 1: Collect labels and strip comments
        pc = 0
        for line in lines:
            line = re.sub(r"#.*$", "", line).strip()
            if not line:
                continue
            if line.endswith(":"):
                label_name = line[:-1].strip()
                labels[label_name] = pc
            else:
                clean_lines.append((pc, line))
                pc += 1

        # Pass 2: Assemble instructions
        bytecode: list[int] = []
        for curr_pc, line in clean_lines:
            tokens = [t.strip().rstrip(",") for t in line.split() if t.strip()]
            mnemonic = tokens[0].upper()
            if mnemonic not in OPCODE_MAP:
                raise ValueError(f"Unknown instruction '{mnemonic}' at line: {line}")

            op = OPCODE_MAP[mnemonic]
            operand_count = len(tokens) - 1
            if op in (Opcode.NOP, Opcode.JOIN, Opcode.BAR_SYNC, Opcode.HALT):
                valid_operand_counts = {0}
            elif op in (Opcode.GET_TID, Opcode.GET_BID):
                valid_operand_counts = {1}
            elif op in (
                Opcode.VADD,
                Opcode.VSUB,
                Opcode.VMUL,
                Opcode.VAND,
                Opcode.VOR,
                Opcode.VXOR,
                Opcode.VFADD,
                Opcode.VFSUB,
                Opcode.VFMUL,
            ):
                valid_operand_counts = {3}
            elif op == Opcode.VFFMA or op == Opcode.MMA_SYNC:
                valid_operand_counts = {4}
            elif op in (Opcode.VLOAD_G, Opcode.VLOAD_S, Opcode.VSTORE_G, Opcode.VSTORE_S):
                valid_operand_counts = {2, 3}
            else:
                valid_operand_counts = {1, 2}
            if operand_count not in valid_operand_counts:
                expected = ", ".join(str(count) for count in sorted(valid_operand_counts))
                raise ValueError(
                    f"{mnemonic} expects {expected} operand(s), got {operand_count} at line: {line}"
                )

            rd = rs1 = rs2 = rs3 = imm = 0

            if op in (Opcode.NOP, Opcode.JOIN, Opcode.BAR_SYNC, Opcode.HALT):
                pass
            elif op in (Opcode.GET_TID, Opcode.GET_BID):
                rd = parse_reg(tokens[1])
            elif op in (
                Opcode.VADD,
                Opcode.VSUB,
                Opcode.VMUL,
                Opcode.VAND,
                Opcode.VOR,
                Opcode.VXOR,
                Opcode.VFADD,
                Opcode.VFSUB,
                Opcode.VFMUL,
            ):
                rd = parse_reg(tokens[1])
                rs1 = parse_reg(tokens[2])
                rs2 = parse_reg(tokens[3])
            elif op == Opcode.VFFMA:
                rd = parse_reg(tokens[1])
                rs1 = parse_reg(tokens[2])
                rs2 = parse_reg(tokens[3])
                rs3 = parse_reg(tokens[4])
            elif op in (Opcode.VLOAD_G, Opcode.VLOAD_S):
                rd = parse_reg(tokens[1])
                rs1 = parse_reg(tokens[2])  # Base address reg
                if len(tokens) > 3:
                    imm = int(tokens[3])
            elif op in (Opcode.VSTORE_G, Opcode.VSTORE_S):
                rs1 = parse_reg(tokens[1])  # Base address reg
                rs2 = parse_reg(tokens[2])  # Value to store
                if len(tokens) > 3:
                    imm = int(tokens[3])
            elif op in (Opcode.BRA, Opcode.BRA_DIV):
                target = tokens[1]
                if target in labels:
                    imm = labels[target] - curr_pc
                else:
                    imm = int(target)
                if len(tokens) > 2:
                    rs1 = parse_reg(tokens[2])  # Condition register
            elif op == Opcode.MMA_SYNC:
                rd = parse_reg(tokens[1])
                rs1 = parse_reg(tokens[2])
                rs2 = parse_reg(tokens[3])
                rs3 = parse_reg(tokens[4])

            inst = Instruction(op=op, rd=rd, rs1=rs1, rs2=rs2, rs3=rs3, imm=imm)
            bytecode.append(inst.encode())

        return bytecode
