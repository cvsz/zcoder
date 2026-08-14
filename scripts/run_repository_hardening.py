#!/usr/bin/env python3
"""Run the one-shot hardening migration with robust generated-code rewrites."""
from __future__ import annotations

import apply_repository_hardening as migration


EXEC_BLOCKS = {
    "src/zcoder/claude/integrations/excel.py": (
        '''            exec(compile(code, "<excel-turn>", "exec"), {"__builtins__": {
                "len": len, "range": range, "sum": sum, "min": min, "max": max,
                "round": round, "sorted": sorted, "list": list, "dict": dict,
                "str": str, "int": int, "float": float, "bool": bool,
                "enumerate": enumerate, "zip": zip, "abs": abs,
            }}, local_ns)''',
        '''            execute_restricted_code(code, {"__builtins__": {
                "len": len, "range": range, "sum": sum, "min": min, "max": max,
                "round": round, "sorted": sorted, "list": list, "dict": dict,
                "str": str, "int": int, "float": float, "bool": bool,
                "enumerate": enumerate, "zip": zip, "abs": abs,
            }}, local_ns, filename="<excel-turn>")''',
    ),
    "src/zcoder/claude/integrations/powerpoint.py": (
        '''            exec(compile(code, "<pptx-turn>", "exec"), {"__builtins__": {
                "len": len, "range": range, "sum": sum, "min": min, "max": max,
                "round": round, "sorted": sorted, "list": list, "dict": dict,
                "str": str, "int": int, "float": float, "bool": bool,
                "enumerate": enumerate, "zip": zip, "abs": abs,
            }}, local_ns)''',
        '''            execute_restricted_code(code, {"__builtins__": {
                "len": len, "range": range, "sum": sum, "min": min, "max": max,
                "round": round, "sorted": sorted, "list": list, "dict": dict,
                "str": str, "int": int, "float": float, "bool": bool,
                "enumerate": enumerate, "zip": zip, "abs": abs,
            }}, local_ns, filename="<pptx-turn>")''',
    ),
}


def harden_generated_code() -> None:
    for path, (old, new) in EXEC_BLOCKS.items():
        text = migration.read(path)
        if old not in text:
            raise RuntimeError(f"expected generated-code block not found in {path}")
        text = text.replace(old, new, 1)
        text = migration.add_import(
            text, "from zcoder.core.restricted_exec import execute_restricted_code"
        )
        migration.write(path, text)


def main() -> None:
    migration.harden_generated_code = harden_generated_code
    migration.main()


if __name__ == "__main__":
    main()
