from __future__ import annotations

import ast
from pathlib import Path

SRC_ROOT = Path("src/zcoder")


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module)
            if node.level:
                imports.update(alias.name for alias in node.names)
    return imports


def _python_files(layer: str) -> list[Path]:
    return sorted((SRC_ROOT / layer).rglob("*.py"))


def _assert_no_infrastructure_dependency(layer: str) -> None:
    violations: list[str] = []
    for path in _python_files(layer):
        for imported in _imports(path):
            if imported == "zcoder.infrastructure" or imported.startswith(
                "zcoder.infrastructure."
            ):
                violations.append(f"{path}: {imported}")
    assert not violations, "forbidden infrastructure dependency:\n" + "\n".join(
        violations
    )


def test_domain_does_not_import_infrastructure():
    _assert_no_infrastructure_dependency("domain")


def test_core_does_not_import_concrete_infrastructure_adapters():
    _assert_no_infrastructure_dependency("core")
