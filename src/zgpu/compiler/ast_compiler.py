"""Advanced Python AST to zISA Vectorized JIT Compiler."""

from __future__ import annotations

import ast
import inspect
import textwrap
from collections.abc import Callable

from zgpu.isa.assembler import Assembler


class AstJitCompiler:
    """Compiles Python functions into vectorized 32-lane zISA assembly & bytecode."""

    def __init__(self):
        self.reg_map: dict[str, str] = {}
        self.next_reg = 12

    @staticmethod
    def compile_expression(expression: str) -> str:
        """Compile a restricted elementwise expression without evaluating Python."""
        if not isinstance(expression, str) or len(expression) > 256:
            raise ValueError("expression must be a string of at most 256 characters")
        if any(character in expression for character in "\r\n#"):
            raise ValueError("expression must be a single line without comments")
        try:
            parsed = ast.parse(expression, mode="eval")
        except SyntaxError as exc:
            raise ValueError("expression must use the form a + b, a - b, or a * b") from exc

        root = parsed.body
        supported = {ast.Add: "VFADD", ast.Sub: "VFSUB", ast.Mult: "VFMUL"}
        if (
            not isinstance(root, ast.BinOp)
            or type(root.op) not in supported
            or not isinstance(root.left, ast.Name)
            or not isinstance(root.right, ast.Name)
            or root.left.id not in {"a", "b"}
            or root.right.id not in {"a", "b"}
        ):
            raise ValueError("expression must use only a and b with +, -, or *")

        instruction = supported[type(root.op)]
        left_register = "R9" if root.left.id == "a" else "R10"
        right_register = "R9" if root.right.id == "a" else "R10"
        return f"""# zGPU elementwise expression
GET.TID R0
VMUL R5, R0, R1
VADD R6, R3, R5
VADD R7, R4, R5
VADD R8, R2, R5
VLOAD.G R9, R6, 0
VLOAD.G R10, R7, 0
{instruction} R11, {left_register}, {right_register}
VSTORE.G R8, R11, 0
HALT"""

    def compile_binary_expr(self, func: Callable) -> str:
        """Parses a Python elementwise arithmetic function and generates zISA."""
        try:
            src = textwrap.dedent(inspect.getsource(func))
        except OSError:
            # Fallback: disassemble isn't possible (e.g. pytest dynamic defs),
            # introspect via dis bytecode to detect the operation type.
            import dis

            bytecode = dis.Bytecode(func)
            op_name = "BINARY_ADD"
            for instr in bytecode:
                if instr.opname.startswith("BINARY_"):
                    op_name = instr.opname
                    break
            op_map = {
                "BINARY_ADD": ast.Add,
                "BINARY_SUBTRACT": ast.Sub,
                "BINARY_MULTIPLY": ast.Mult,
            }
            op_cls = op_map.get(op_name, ast.Add)
            # Build a synthetic AST
            fn_name = getattr(func, "__name__", "anonymous")
            params = list(inspect.signature(func).parameters.keys())
            fn_def = ast.FunctionDef(
                name=fn_name,
                args=ast.arguments(
                    posonlyargs=[],
                    args=[ast.arg(arg=p) for p in params],
                    vararg=None,
                    kwonlyargs=[],
                    kw_defaults=[],
                    kwarg=None,
                    defaults=[],
                ),
                body=[
                    ast.Return(
                        value=ast.BinOp(
                            left=ast.Name(id=params[1] if len(params) > 1 else "a"),
                            op=op_cls(),
                            right=ast.Name(id=params[2] if len(params) > 2 else "b"),
                        )
                    )
                ],
                decorator_list=[],
            )
            tree = ast.Module(body=[fn_def], type_ignores=[])
        else:
            tree = ast.parse(src)
        fn_def = tree.body[0]
        assert isinstance(fn_def, ast.FunctionDef)

        # Determine operator
        ret_stmt = None
        for stmt in fn_def.body:
            if isinstance(stmt, ast.Return):
                ret_stmt = stmt
                break

        inst = "VFADD"
        if ret_stmt and isinstance(ret_stmt.value, ast.BinOp):
            op = ret_stmt.value.op
            if isinstance(op, ast.Add):
                inst = "VFADD"
            elif isinstance(op, ast.Sub):
                inst = "VFSUB"
            elif isinstance(op, ast.Mult):
                inst = "VFMUL"

        zisa_code = f"""
        # Compiled from Python: {fn_def.name}
        # Vectorized 32-Lane SIMT Kernel
        VMUL R5, R0, R1         # byte_offset = tid * stride
        VADD R6, R3, R5         # addr_a = base_a + offset
        VADD R7, R4, R5         # addr_b = base_b + offset
        VADD R8, R2, R5         # addr_out = base_out + offset

        VLOAD.G R9, R6, 0       # val_a = *addr_a
        VLOAD.G R10, R7, 0      # val_b = *addr_b
        {inst} R11, R9, R10     # compute operation
        VSTORE.G R8, R11, 0     # *addr_out = result
        HALT
        """
        return zisa_code.strip()

    def compile_to_bytecode(self, source: str) -> list[int]:
        return Assembler.assemble(source)
