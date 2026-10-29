"""zCompiler Command-Line Interface."""

from __future__ import annotations

import argparse

from zgpu.isa.assembler import Assembler


def main():
    parser = argparse.ArgumentParser(description="zGPU JIT & Assembly Compiler (zcc)")
    parser.add_argument("input_file", help="Input zISA assembly or high-level source file")
    parser.add_argument("-o", "--output", default="kernel.bin", help="Output binary bytecode file")
    parser.add_argument("--disasm", action="store_true", help="Disassemble binary bytecode")

    args = parser.parse_args()

    with open(args.input_file) as f:
        src = f.read()

    bytecode = Assembler.assemble(src)
    with open(args.output, "wb") as f:
        for word in bytecode:
            f.write(word.to_bytes(4, byteorder="little"))

    print(f"✅ Successfully compiled {len(bytecode)} instructions to '{args.output}'.")


if __name__ == "__main__":
    main()
