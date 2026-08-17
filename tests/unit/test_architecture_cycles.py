from __future__ import annotations

import ast
from pathlib import Path

SRC_ROOT = Path("src/zcoder")


def _module_name(path: Path) -> str:
    relative = path.relative_to(SRC_ROOT.parent).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _module_paths() -> dict[str, Path]:
    return {_module_name(path): path for path in sorted(SRC_ROOT.rglob("*.py"))}


def _resolve_from_import(module: str, path: Path, node: ast.ImportFrom) -> list[str]:
    if node.level == 0:
        base = node.module or ""
    else:
        package = module if path.name == "__init__.py" else module.rpartition(".")[0]
        parts = package.split(".") if package else []
        keep = max(0, len(parts) - (node.level - 1))
        prefix = parts[:keep]
        if node.module:
            prefix.extend(node.module.split("."))
        base = ".".join(prefix)

    candidates = [base] if base else []
    candidates.extend(f"{base}.{alias.name}" if base else alias.name for alias in node.names)
    return candidates


def _dependency_graph() -> dict[str, set[str]]:
    modules = _module_paths()
    graph: dict[str, set[str]] = {module: set() for module in modules}

    for module, path in modules.items():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            candidates: list[str] = []
            if isinstance(node, ast.Import):
                candidates.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                candidates.extend(_resolve_from_import(module, path, node))

            for candidate in candidates:
                if candidate in modules and candidate != module:
                    graph[module].add(candidate)

    return graph


def _find_cycle(graph: dict[str, set[str]]) -> list[str] | None:
    visited: set[str] = set()
    active: set[str] = set()
    stack: list[str] = []

    def visit(module: str) -> list[str] | None:
        if module in active:
            start = stack.index(module)
            return stack[start:] + [module]
        if module in visited:
            return None

        visited.add(module)
        active.add(module)
        stack.append(module)
        for dependency in sorted(graph[module]):
            cycle = visit(dependency)
            if cycle:
                return cycle
        stack.pop()
        active.remove(module)
        return None

    for module in sorted(graph):
        cycle = visit(module)
        if cycle:
            return cycle
    return None


def test_canonical_package_has_no_static_import_cycles():
    cycle = _find_cycle(_dependency_graph())
    assert cycle is None, "circular import detected: " + " -> ".join(cycle or [])
