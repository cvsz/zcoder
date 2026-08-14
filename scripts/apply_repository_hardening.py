#!/usr/bin/env python3
"""One-shot repository hardening migration.

This script is intentionally deterministic: it rewrites known security
primitives, dependency metadata, active documentation, and GitHub repository
metadata. It is used on a review branch and can be removed after the migration.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "zcoder"


def read(path: str | Path) -> str:
    return (ROOT / path).read_text(encoding="utf-8") if isinstance(path, str) else path.read_text(encoding="utf-8")


def write(path: str | Path, content: str) -> None:
    target = ROOT / path if isinstance(path, str) else path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content.rstrip() + "\n", encoding="utf-8")


def replace_required(path: str, old: str, new: str) -> None:
    text = read(path)
    if old not in text:
        raise RuntimeError(f"expected pattern not found in {path}: {old[:80]!r}")
    write(path, text.replace(old, new))


def add_import(text: str, import_line: str) -> str:
    if import_line in text:
        return text
    lines = text.splitlines()
    idx = 0
    if lines and lines[0].startswith(("\"\"\"", "'''")):
        quote = lines[0][:3]
        if lines[0].count(quote) >= 2 and len(lines[0].strip()) > 6:
            idx = 1
        else:
            idx = 1
            while idx < len(lines):
                if quote in lines[idx]:
                    idx += 1
                    break
                idx += 1
    while idx < len(lines) and (lines[idx].startswith("from __future__") or not lines[idx].strip()):
        idx += 1
    lines.insert(idx, import_line)
    return "\n".join(lines) + "\n"


def upsert_block(path: str, key: str, block: str) -> None:
    text = read(path)
    start = f"<!-- zcoder:{key}:start -->"
    end = f"<!-- zcoder:{key}:end -->"
    payload = f"{start}\n{block.strip()}\n{end}"
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.DOTALL)
    if pattern.search(text):
        text = pattern.sub(payload, text)
    else:
        lines = text.splitlines()
        insert_at = 1 if lines and lines[0].startswith("#") else 0
        lines[insert_at:insert_at] = ["", payload, ""]
        text = "\n".join(lines)
    write(path, text)


def create_security_helpers() -> None:
    write(
        "src/zcoder/core/safe_io.py",
        '''"""Validated network I/O helpers used by ZCoder integrations."""
from __future__ import annotations

import urllib.request
from typing import Any
from urllib.parse import urlsplit

_ALLOWED_SCHEMES = frozenset({"http", "https"})


def _target_url(target: Any) -> str:
    return str(getattr(target, "full_url", target))


def validate_http_url(target: Any) -> str:
    """Require an absolute HTTP(S) URL before opening a network resource."""
    url = _target_url(target)
    parsed = urlsplit(url)
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        raise ValueError(f"unsupported URL scheme: {parsed.scheme or '<missing>'}")
    if not parsed.hostname:
        raise ValueError("network URL must include a hostname")
    if parsed.username or parsed.password:
        raise ValueError("credentials embedded in URLs are not permitted")
    return url


def safe_urlopen(target: Any, *, timeout: float = 30):
    """Open only a validated absolute HTTP(S) URL.

    urllib itself supports file/custom schemes, which is why Bandit flags a raw
    urlopen call. This boundary validates the scheme and authority first.
    """
    validate_http_url(target)
    return urllib.request.urlopen(target, timeout=timeout)  # nosec B310 -- scheme and authority validated above
''',
    )
    write(
        "src/zcoder/core/safe_subprocess.py",
        '''"""Shell-free subprocess execution helpers."""
from __future__ import annotations

import os
import shlex
import subprocess
from collections.abc import Sequence
from typing import Any


def command_argv(command: str | Sequence[str]) -> list[str]:
    """Convert a command to argv without invoking a shell."""
    if isinstance(command, str):
        argv = shlex.split(command, posix=os.name != "nt")
    else:
        argv = [str(part) for part in command]
    if not argv:
        raise ValueError("command must not be empty")
    return argv


def run_command(command: str | Sequence[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    """Run a command directly; pipes/redirection require an explicit executable."""
    kwargs.pop("shell", None)
    return subprocess.run(command_argv(command), shell=False, **kwargs)
''',
    )
    write(
        "src/zcoder/core/restricted_exec.py",
        '''"""AST validation for narrowly scoped model-generated Python snippets.

This is a defense-in-depth boundary, not an OS sandbox. Code that requires
untrusted arbitrary execution must use the dedicated ZCoder sandbox runtime.
"""
from __future__ import annotations

import ast
from collections.abc import Mapping, MutableMapping
from typing import Any

_FORBIDDEN_NODES = (
    ast.Import,
    ast.ImportFrom,
    ast.Global,
    ast.Nonlocal,
    ast.Lambda,
    ast.ClassDef,
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.With,
    ast.AsyncWith,
    ast.While,
)
_FORBIDDEN_NAMES = frozenset(
    {
        "__import__",
        "breakpoint",
        "compile",
        "delattr",
        "dir",
        "eval",
        "exec",
        "getattr",
        "globals",
        "help",
        "input",
        "locals",
        "open",
        "setattr",
        "type",
        "vars",
    }
)


class RestrictedCodeError(ValueError):
    """Raised when generated code crosses the restricted execution policy."""


class _PolicyVisitor(ast.NodeVisitor):
    def generic_visit(self, node: ast.AST) -> None:
        if isinstance(node, _FORBIDDEN_NODES):
            raise RestrictedCodeError(f"disallowed syntax: {type(node).__name__}")
        super().generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id.startswith("_") or node.id in _FORBIDDEN_NAMES:
            raise RestrictedCodeError(f"disallowed name: {node.id}")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr.startswith("_"):
            raise RestrictedCodeError(f"disallowed attribute: {node.attr}")
        self.generic_visit(node)


def execute_restricted_code(
    code: str,
    globals_ns: Mapping[str, Any],
    locals_ns: MutableMapping[str, Any],
    *,
    filename: str = "<generated>",
) -> None:
    """Validate then execute a small capability-scoped Python snippet."""
    tree = ast.parse(code, filename=filename, mode="exec")
    _PolicyVisitor().visit(tree)
    compiled = compile(tree, filename, "exec")
    exec(compiled, dict(globals_ns), locals_ns)  # nosec B102 -- AST policy and caller-provided capabilities enforced above
''',
    )
    write(
        "src/zcoder/core/temp_paths.py",
        '''"""Cross-platform temporary-directory helpers."""
from __future__ import annotations

import tempfile
from pathlib import Path


def default_temp_dir(name: str) -> str:
    if not name or any(part in {"..", "."} for part in Path(name).parts):
        raise ValueError("temporary directory name must be a simple relative name")
    return str(Path(tempfile.gettempdir()) / name)
''',
    )


def harden_network_calls() -> None:
    helper = SRC / "core" / "safe_io.py"
    for path in SRC.rglob("*.py"):
        if path == helper:
            continue
        text = path.read_text(encoding="utf-8")
        if "urllib.request.urlopen(" not in text:
            continue
        text = text.replace("urllib.request.urlopen(", "safe_urlopen(")
        text = add_import(text, "from zcoder.core.safe_io import safe_urlopen")
        write(path, text)


def harden_shell_calls() -> None:
    helper = SRC / "core" / "safe_subprocess.py"
    for path in SRC.rglob("*.py"):
        if path == helper:
            continue
        text = path.read_text(encoding="utf-8")
        if not re.search(r"shell\s*=\s*True", text):
            continue
        text = text.replace("subprocess.run(", "run_command(")
        text = re.sub(r"\bshell\s*=\s*True\s*,?\s*", "", text)
        text = add_import(text, "from zcoder.core.safe_subprocess import run_command")
        write(path, text)


def harden_generated_code() -> None:
    targets = {
        "src/zcoder/claude/integrations/excel.py": "<excel-turn>",
        "src/zcoder/claude/integrations/powerpoint.py": "<pptx-turn>",
    }
    for path, filename in targets.items():
        text = read(path)
        old = f'exec(compile(code, "{filename}", "exec"), {{"__builtins__": {{'
        new = 'execute_restricted_code(code, {"__builtins__": {'
        if old not in text:
            raise RuntimeError(f"expected direct exec not found in {path}")
        text = text.replace(old, new)
        # Existing call closes with `}}, local_ns)`. Add the keyword filename to
        # the first matching generated-code call only.
        needle = "            }}, local_ns)"
        replacement = f'            }}, local_ns, filename="{filename}")'
        if needle not in text:
            raise RuntimeError(f"expected exec call terminator not found in {path}")
        text = text.replace(needle, replacement, 1)
        text = add_import(text, "from zcoder.core.restricted_exec import execute_restricted_code")
        write(path, text)


def harden_temp_paths() -> None:
    replacements = {
        "src/zcoder/enterprise/local_ai_stack.py": {
            '"/tmp/zcoder_models"': 'default_temp_dir("zcoder_models")',
            '"/tmp/zcoder_worktrees"': 'default_temp_dir("zcoder_worktrees")',
        },
        "src/zcoder/enterprise/no_cost_platform.py": {
            '"/tmp/zcoder_local_storage"': 'default_temp_dir("zcoder_local_storage")',
        },
    }
    for path, mapping in replacements.items():
        text = read(path)
        for old, new in mapping.items():
            if old not in text:
                raise RuntimeError(f"expected temp path not found in {path}: {old}")
            text = text.replace(old, new)
        text = add_import(text, "from zcoder.core.temp_paths import default_temp_dir")
        write(path, text)


def harden_sql() -> None:
    path = "src/zcoder/domain/services/deployment.py"
    text = read(path)
    old = '''            for table in ["jobs", "outbox", "webhook_inbox", "installations", "repositories"]:
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                records[table] = cur.fetchone()[0]'''
    new = '''            table_count_queries = {
                "jobs": "SELECT COUNT(*) FROM jobs",
                "outbox": "SELECT COUNT(*) FROM outbox",
                "webhook_inbox": "SELECT COUNT(*) FROM webhook_inbox",
                "installations": "SELECT COUNT(*) FROM installations",
                "repositories": "SELECT COUNT(*) FROM repositories",
            }
            for table, query in table_count_queries.items():
                cur.execute(query)
                records[table] = cur.fetchone()[0]'''
    if old not in text:
        raise RuntimeError("expected deployment table-count query not found")
    write(path, text.replace(old, new))


def update_dependencies() -> None:
    path = "pyproject.toml"
    text = read(path)
    if 'postgres = ["psycopg2-binary>=2.9.9,<3"]' not in text:
        marker = 'pptx = ["python-pptx>=0.6.23"]\n'
        if marker not in text:
            raise RuntimeError("pyproject pptx extra marker missing")
        text = text.replace(marker, marker + 'postgres = ["psycopg2-binary>=2.9.9,<3"]\n')
    all_block = '''all = [
    "fastapi>=0.100.0",
    "uvicorn>=0.23.0",
    "starlette>=0.27.0",
]'''
    all_new = '''all = [
    "fastapi>=0.100.0",
    "uvicorn>=0.23.0",
    "starlette>=0.27.0",
    "psycopg2-binary>=2.9.9,<3",
]'''
    if all_block in text:
        text = text.replace(all_block, all_new)
    dev_marker = '    "bandit>=1.7.9",\n]'
    if '    "psycopg2-binary>=2.9.9,<3",\n]' not in text:
        if dev_marker not in text:
            raise RuntimeError("pyproject dev extra marker missing")
        text = text.replace(dev_marker, '    "bandit>=1.7.9",\n    "psycopg2-binary>=2.9.9,<3",\n]')
    write(path, text)

    req = read("requirements-dev.txt")
    if "psycopg2-binary" not in req:
        req += "\n# PostgreSQL integration tests and optional production adapter\npsycopg2-binary>=2.9.9,<3\n"
    write("requirements-dev.txt", req)


def github_files() -> None:
    write(".github/CODEOWNERS", "* @cvsz\n")
    write(
        ".github/PULL_REQUEST_TEMPLATE.md",
        '''## Summary

Describe the problem and the production impact of this change.

## Change type

- [ ] Feature
- [ ] Bug fix
- [ ] Security hardening
- [ ] Refactor
- [ ] Documentation / governance
- [ ] Build / CI / dependency change

## Validation

- [ ] `make check` (or equivalent focused checks) passes locally
- [ ] Tests were added or updated for behavior changes
- [ ] Security and tenant/isolation implications were reviewed
- [ ] Documentation and changelog were updated when user/operator behavior changed
- [ ] Backward compatibility was preserved or the migration is documented

## Operational impact

List deployment, rollback, migration, observability, cost, or reliability considerations. Use `None` when not applicable.
''',
    )
    write(
        ".github/ISSUE_TEMPLATE/bug_report.yml",
        '''name: Bug report
description: Report a reproducible defect in ZCoder
title: "bug: "
labels: ["bug"]
body:
  - type: markdown
    attributes:
      value: "Do not report security vulnerabilities here; use the private security reporting path in SECURITY.md."
  - type: textarea
    id: summary
    attributes:
      label: Summary
      description: What happened and what did you expect?
    validations:
      required: true
  - type: textarea
    id: reproduce
    attributes:
      label: Reproduction
      description: Minimal commands, inputs, or test case.
    validations:
      required: true
  - type: input
    id: version
    attributes:
      label: ZCoder version / commit
    validations:
      required: true
  - type: textarea
    id: environment
    attributes:
      label: Environment
      description: OS, Python version, deployment mode, and relevant provider/runtime.
  - type: textarea
    id: logs
    attributes:
      label: Sanitized logs
      description: Remove credentials, tokens, customer data, and private prompts.
''',
    )
    write(
        ".github/ISSUE_TEMPLATE/feature_request.yml",
        '''name: Feature request
description: Propose a production-facing capability or improvement
title: "feat: "
labels: ["enhancement"]
body:
  - type: textarea
    id: problem
    attributes:
      label: Problem
      description: What user or operator problem should be solved?
    validations:
      required: true
  - type: textarea
    id: outcome
    attributes:
      label: Desired outcome
      description: Define observable acceptance criteria rather than only an implementation idea.
    validations:
      required: true
  - type: textarea
    id: constraints
    attributes:
      label: Constraints and trade-offs
      description: Security, compatibility, provider, cost, performance, or operational constraints.
  - type: textarea
    id: alternatives
    attributes:
      label: Alternatives considered
''',
    )
    write(
        ".github/ISSUE_TEMPLATE/documentation.yml",
        '''name: Documentation issue
description: Report missing, stale, ambiguous, or incorrect documentation
title: "docs: "
labels: ["documentation"]
body:
  - type: input
    id: location
    attributes:
      label: Document or section
      placeholder: docs/security/IDENTITY.md
    validations:
      required: true
  - type: textarea
    id: issue
    attributes:
      label: What is incorrect or missing?
    validations:
      required: true
  - type: textarea
    id: proposed
    attributes:
      label: Proposed correction
''',
    )
    write(
        ".github/ISSUE_TEMPLATE/config.yml",
        '''blank_issues_enabled: false
contact_links:
  - name: Security vulnerability
    url: https://github.com/cvsz/zcoder/security/advisories/new
    about: Report vulnerabilities privately. Do not open a public issue.
''',
    )
    write(
        ".github/dependabot.yml",
        '''version: 2
updates:
  - package-ecosystem: pip
    directory: "/"
    schedule:
      interval: weekly
      day: monday
    open-pull-requests-limit: 10
    labels: ["dependencies", "python"]
  - package-ecosystem: github-actions
    directory: "/"
    schedule:
      interval: weekly
      day: monday
    open-pull-requests-limit: 10
    labels: ["dependencies", "github-actions"]
''',
    )


def workflows() -> None:
    write(
        ".github/workflows/ci.yml",
        '''name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

concurrency:
  group: ci-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

permissions:
  contents: read

env:
  PIP_DISABLE_PIP_VERSION_CHECK: "1"

jobs:
  quality:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v7
        with:
          python-version: "3.12"
          cache: pip
          cache-dependency-path: |
            pyproject.toml
            requirements*.txt
      - run: python -m pip install -e ".[dev]"
      - run: ruff check src tests scripts
      - run: black --check src tests scripts
      - run: python -m compileall -q src

  security:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v7
        with:
          python-version: "3.12"
          cache: pip
          cache-dependency-path: |
            pyproject.toml
            requirements*.txt
      - run: python -m pip install -e ".[dev]"
      - run: bandit -r src/zcoder -ll

  test:
    runs-on: ubuntu-24.04
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.9", "3.10", "3.11", "3.12"]
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v7
        with:
          python-version: ${{ matrix.python-version }}
          cache: pip
          cache-dependency-path: |
            pyproject.toml
            requirements*.txt
      - run: python -m pip install -e ".[dev]"
      - name: Import compatibility smoke test
        run: |
          python -c "import zcoder, zcoder.main, coder, claude_models, config; assert coder.__name__ == 'zcoder.services.coder'; print(zcoder.__version__)"
      - run: pytest --cov --cov-report=xml --cov-report=term-missing
      - uses: actions/upload-artifact@v7
        if: matrix.python-version == '3.12'
        with:
          name: coverage-report
          path: coverage.xml

  docker-build:
    runs-on: ubuntu-24.04
    needs: [quality, security, test]
    steps:
      - uses: actions/checkout@v7
      - run: docker build -t zcoder:ci .
      - run: docker run --rm zcoder:ci --version
''',
    )
    write(
        ".github/workflows/docs.yml",
        '''name: Documentation

on:
  push:
    branches: [main]
    paths:
      - "**/*.md"
      - "scripts/check_docs.py"
      - ".github/workflows/docs.yml"
  pull_request:
    branches: [main]
    paths:
      - "**/*.md"
      - "scripts/check_docs.py"
      - ".github/workflows/docs.yml"

permissions:
  contents: read

jobs:
  validate:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v7
        with:
          python-version: "3.12"
      - run: python scripts/check_docs.py
''',
    )
    write(
        ".github/workflows/package.yml",
        '''name: Package

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  contents: read

jobs:
  wheel-smoke:
    runs-on: ubuntu-24.04
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.9", "3.12"]
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v7
        with:
          python-version: ${{ matrix.python-version }}
      - run: python -m pip install --upgrade build
      - run: python -m build
      - run: python -m pip install dist/*.whl
      - run: python -m pip check
      - run: python -c "import zcoder, zcoder.main, coder, claude_models; print(zcoder.__version__)"
      - run: python -m zcoder.main --health-check
      - uses: actions/upload-artifact@v7
        if: matrix.python-version == '3.12'
        with:
          name: python-package
          path: dist/*
''',
    )
    write(
        ".github/workflows/dependency-audit.yml",
        '''name: Dependency audit

on:
  workflow_dispatch:
  schedule:
    - cron: "17 3 * * 1"

permissions:
  contents: read

jobs:
  pip-audit:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v7
        with:
          python-version: "3.12"
          cache: pip
      - run: python -m pip install -e ".[dev]" pip-audit
      - run: pip-audit
''',
    )


def documentation_files() -> None:
    write(
        "CODE_OF_CONDUCT.md",
        '''# Code of Conduct

## Our standard

ZCoder contributors are expected to communicate professionally, assume good faith, focus review on technical substance, and maintain an environment free from harassment, threats, discrimination, doxxing, or abusive behavior.

## Scope

This standard applies to repository issues, pull requests, reviews, discussions, release coordination, and other project spaces where a participant represents the project.

## Enforcement

Maintainers may edit or remove content, close interactions, restrict participation, or escalate serious conduct or security concerns when behavior undermines a safe and productive engineering environment.

## Reporting

Report conduct concerns privately to the repository maintainers. Security vulnerabilities must follow [SECURITY.md](SECURITY.md) and must not be disclosed through public issues.
''',
    )
    write(
        "GOVERNANCE.md",
        '''# Governance

ZCoder is maintained under the `cvsz` repository ownership boundary. The `main` branch is the release source of truth.

## Decision model

- Maintainers own release, security, architecture, and compatibility decisions.
- Material changes should arrive through pull requests with automated validation.
- Architectural decisions must preserve the dependency direction documented in [ARCHITECTURE.md](ARCHITECTURE.md).
- Security-sensitive changes require explicit consideration of command execution, network boundaries, credentials, tenant isolation, and persistence.
- Historical upgrade records remain immutable in meaning even when current paths move.

## Merge standard

A change is mergeable when required CI, security, tests, documentation validation, and package smoke checks have actually executed successfully, or when an explicitly documented repository policy permits an exception. A skipped or unavailable runner is not evidence of a pass.

## Releases

Release versions are defined by package metadata and the canonical runtime. Release notes belong in [CHANGELOG.md](CHANGELOG.md); historical implementation/audit notes live under `docs/upgrades/`.
''',
    )
    write(
        "SUPPORT.md",
        '''# Support

## Before opening an issue

1. Confirm the behavior on a supported Python version (3.9-3.12 for the current v1.40 package contract).
2. Run `zcoder --health-check` or `python -m zcoder.main --health-check`.
3. Check [QUICKSTART.md](QUICKSTART.md), [docs/README.md](docs/README.md), and existing issues.
4. Remove API keys, tokens, customer data, private prompts, and credentials from logs.

Use the structured GitHub issue forms for reproducible bugs, feature requests, and documentation defects.

## Security

Do **not** open a public issue for a vulnerability. Follow [SECURITY.md](SECURITY.md) and use GitHub private vulnerability reporting / security advisories where available.
''',
    )
    category_docs = {
        "docs/security/README.md": ("Security", "Identity, credentials, encryption, key management, SSO, SCIM, service accounts, and security runbooks."),
        "docs/compliance/README.md": ("Compliance", "Audit evidence, policies, retention, residency, quotas, controls, and multi-tenant compliance boundaries."),
        "docs/operations/README.md": ("Operations", "Deployment, observability, SLOs, disaster recovery, Kubernetes, billing, metering, and incident runbooks."),
        "docs/enterprise/README.md": ("Enterprise", "Enterprise feature, RBAC, organization, and MCP conformance documentation."),
        "docs/guides/README.md": ("Guides", "Operator and developer guides for local AI, projects/artifacts, and advanced model workflows."),
        "docs/upgrades/README.md": ("Upgrade archive", "Historical release, audit, and implementation records. These documents preserve the architecture and paths that existed at the time; use current root/docs indexes for authoritative paths."),
        "docs/prompts/README.md": ("Prompt archive", "Historical upgrade/audit prompts retained as project provenance. They are not current implementation instructions unless explicitly referenced by a current plan."),
    }
    for path, (title, desc) in category_docs.items():
        folder = ROOT / path
        entries = sorted(
            p.name for p in folder.parent.iterdir() if p.is_file() and p.name.lower() != "readme.md"
        ) if folder.parent.exists() else []
        listing = "\n".join(f"- `{name}`" for name in entries) or "- No indexed files yet."
        write(path, f"# {title}\n\n{desc}\n\n## Contents\n\n{listing}\n")

    broken = ROOT / "docs/upgrades/19_upgrade_v1.10.0.md"
    if not broken.exists() or not broken.read_text(encoding="utf-8", errors="ignore").strip():
        write(
            broken,
            '''# Upgrade v1.10.0 — Historical record

This archive entry was present in the repository as an empty/truncated file after the source-layout migration. It is restored as an explicit historical marker rather than inventing release claims that cannot be reconstructed from the truncated artifact.

For current architecture and supported entry points, use [../../ARCHITECTURE.md](../../ARCHITECTURE.md) and [../../README.md](../../README.md). Adjacent v1.10.x records in this directory provide the preserved detailed implementation history for that release line.
''',
        )

    upsert_block(
        "README.md",
        "repository-baseline",
        '''## Repository baseline (2026-08-14)

The canonical Python implementation is the `src/zcoder/` package. Installed entry points are `zcoder` and `ai-coder`; root `main.py` and top-level modules under `src/` exist only for compatibility with older integrations.

```bash
python -m pip install -e ".[dev]"
zcoder --health-check
pytest
```

Optional PostgreSQL support is installed with `zcoder[postgres]`. Repository changes are validated by CI, Bandit security scanning, documentation checks, built-wheel smoke tests, and Docker build validation. See [ARCHITECTURE.md](ARCHITECTURE.md), [QUICKSTART.md](QUICKSTART.md), [CONTRIBUTING.md](CONTRIBUTING.md), and the [documentation index](docs/README.md).

> Historical release sections below may mention the compatibility launcher `python main.py`; new automation and documentation should prefer the installed `zcoder` command or `python -m zcoder.main`.
''',
    )
    upsert_block(
        "ARCHITECTURE.md",
        "validation-contract",
        '''## Repository validation contract

The architecture is enforced at repository boundaries as well as runtime boundaries: CI validates the canonical package across Python 3.9-3.12, Bandit blocks Medium/High findings under `src/zcoder`, package checks install the built wheel rather than relying only on editable installs, documentation checks validate the active documentation surface, and Docker is built only after code gates succeed.

Shell commands are executed without implicit shell expansion, outbound urllib integrations pass through a validated HTTP(S) boundary, model-generated Python used by document integrations passes through AST policy validation, and PostgreSQL support is an explicit install extra rather than an undeclared import-time dependency.
''',
    )
    upsert_block(
        "SECURITY.md",
        "secure-development",
        '''## Secure-development baseline

- No provider secret may be sent to browser clients.
- New subprocess execution must use argv-based execution without `shell=True`; explicit shell interpreters are capabilities that require policy review.
- Outbound urllib calls must pass through the validated HTTP(S) helper in `zcoder.core.safe_io`.
- Generated Python is not a trusted boundary. Document integrations use restricted AST validation; arbitrary untrusted execution belongs in the sandbox runtime.
- SQL values must be parameterized and dynamic identifiers must come from explicit allowlists/static query maps.
- Temporary state must use platform temporary-directory APIs rather than hard-coded shared paths.
- CI Bandit scanning remains blocking for Medium and High severity findings.

Report vulnerabilities privately through GitHub Security Advisories / private vulnerability reporting. Never include credentials or customer data in a public issue.
''',
    )
    upsert_block(
        "CONTRIBUTING.md",
        "repository-workflow",
        '''## Current repository workflow

1. Install development dependencies with `python -m pip install -e ".[dev]"`.
2. Add code under `src/zcoder/`; use compatibility aliases only when preserving an existing public import.
3. Put tests in `tests/unit/`, `tests/integration/`, or `tests/e2e/` according to the boundary exercised.
4. Run `ruff check src tests scripts`, `black --check src tests scripts`, `bandit -r src/zcoder -ll`, `pytest`, and `python scripts/check_docs.py` before requesting review.
5. Update active docs and `CHANGELOG.md` when behavior, operations, compatibility, or security posture changes.
6. Do not treat skipped CI jobs, unavailable runners, or stale release-gate evidence as a successful validation result.
''',
    )
    upsert_block(
        "QUICKSTART.md",
        "canonical-quickstart",
        '''## Canonical quick start

```bash
python -m venv venv
# Linux/macOS
source venv/bin/activate
# Windows PowerShell: venv\\Scripts\\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
zcoder --health-check
zcoder --version
```

For PostgreSQL adapters use `python -m pip install -e ".[dev,postgres]"`. For a package-consumer install use `python -m pip install ".[all]"`. The root `python main.py` launcher remains compatibility-only.
''',
    )
    upsert_block(
        "ROADMAP.md",
        "current-status",
        '''## Current repository status

The src-layout migration is complete. The current engineering focus is release evidence and operational hardening: keep all CI gates executing successfully, preserve canonical/legacy import compatibility, maintain explicit dependency extras, expand integration/e2e coverage around sandbox and provider boundaries, and keep active documentation synchronized with code. Historical version/audit records are archived under `docs/upgrades/` rather than used as current architecture guidance.
''',
    )
    upsert_block(
        "CHANGELOG.md",
        "unreleased-hardening",
        '''## Unreleased — Repository hardening

### Changed
- Declared the PostgreSQL adapter dependency through the `postgres`, `all`, and development dependency contracts.
- Replaced implicit-shell command execution with argv-based subprocess execution.
- Centralized validated HTTP(S) urllib access and restricted generated-code execution.
- Replaced hard-coded shared temporary paths and dynamic table-count SQL construction.
- Upgraded GitHub Actions to current Node 24-era major releases and split CI, docs, package, and scheduled dependency-audit responsibilities.

### Documentation and governance
- Added repository governance, support, code-of-conduct, CODEOWNERS, structured issue forms, PR template, Dependabot, category indexes, and documentation validation.
- Restored the truncated v1.10.0 upgrade archive marker without inventing historical release evidence.
''',
    )
    upsert_block(
        "Artifacts-zcoder.md",
        "migration-status",
        '''## Migration execution status

The restructuring proposed by this artifact has been executed. `src/zcoder/` is now canonical, tests are grouped by test boundary, documentation has category indexes, legacy imports are compatibility aliases, and packaging/CLI/Docker entry points resolve through the canonical package. Future architecture changes should be proposed against [ARCHITECTURE.md](ARCHITECTURE.md), not against the pre-migration flat layout captured later in this historical proposal.
''',
    )
    upsert_block(
        "CHECKLIST.md",
        "repository-gates",
        '''## Repository completion gates

- [x] Canonical `src/zcoder` package layout
- [x] Editable/package install metadata
- [x] Python 3.9-3.12 CI matrix
- [x] Blocking lint/format/security gates
- [x] Built-wheel smoke workflow
- [x] Documentation validation workflow
- [x] GitHub issue/PR templates, CODEOWNERS, Dependabot, governance/support documents
- [x] Historical upgrade archive indexed and truncated v1.10.0 marker restored
- [ ] Mark release evidence PASS only after the new workflows execute successfully on the final commit
''',
    )
    upsert_block(
        "IMPLEMENTATION_CHECKLIST.md",
        "repository-hardening",
        '''## Repository-hardening implementation

- [x] PostgreSQL driver declared for development and optional production installs
- [x] shell-free subprocess boundary
- [x] validated HTTP(S) urllib boundary
- [x] restricted generated-code execution boundary
- [x] secure temporary-directory defaults
- [x] static allowlisted table-count queries
- [x] active documentation current-layout banner and archive navigation
- [x] GitHub governance/templates/workflows
- [ ] Final CI evidence recorded only after GitHub Actions executes on the completed branch/main commit
''',
    )
    if (ROOT / "webapp/README.md").exists():
        upsert_block(
            "webapp/README.md",
            "canonical-runtime",
            '''## Canonical runtime integration

The web application is an interface adapter over the canonical `zcoder` package. Development/install automation should install the package (`python -m pip install -e ".[web]"`) and import `zcoder.*`; references to root modules are compatibility paths only. Provider credentials remain server-side and must never be serialized to browser clients.
''',
        )


def update_active_markdown_paths() -> None:
    upgrade_names = {
        p.name: p.relative_to(ROOT).as_posix() for p in (ROOT / "docs/upgrades").glob("*.md")
    }
    test_matches: dict[str, list[str]] = {}
    for p in (ROOT / "tests").rglob("*.py"):
        test_matches.setdefault(p.name, []).append(p.relative_to(ROOT).as_posix())

    for path in ROOT.rglob("*.md"):
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith("docs/upgrades/") or rel.startswith("docs/prompts/"):
            continue
        text = path.read_text(encoding="utf-8")
        for name, current in upgrade_names.items():
            text = text.replace(f"docs/{name}", current)
        for name, matches in test_matches.items():
            if len(matches) == 1:
                text = text.replace(f"tests/{name}", matches[0])
        write(path, text)


def docs_checker() -> None:
    write(
        "scripts/check_docs.py",
        r'''#!/usr/bin/env python3
"""Validate the active Markdown surface and archive integrity."""
from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {
    "README.md",
    "ARCHITECTURE.md",
    "CHANGELOG.md",
    "CODE_OF_CONDUCT.md",
    "CONTRIBUTING.md",
    "GOVERNANCE.md",
    "QUICKSTART.md",
    "ROADMAP.md",
    "SECURITY.md",
    "SUPPORT.md",
    "docs/README.md",
    "docs/security/README.md",
    "docs/compliance/README.md",
    "docs/operations/README.md",
    "docs/enterprise/README.md",
    "docs/guides/README.md",
    "docs/upgrades/README.md",
    "docs/prompts/README.md",
}
ARCHIVE_PREFIXES = ("docs/upgrades/", "docs/prompts/")
LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")


def strip_fenced_code(text: str) -> str:
    return re.sub(r"```.*?```", "", text, flags=re.DOTALL)


def local_target(source: Path, raw: str) -> Path | None:
    target = raw.strip().split()[0].strip("<>")
    if not target or target.startswith(("#", "http://", "https://", "mailto:", "tel:")):
        return None
    target = unquote(target.split("#", 1)[0].split("?", 1)[0])
    if not target:
        return None
    return (source.parent / target).resolve()


def main() -> int:
    errors: list[str] = []
    for required in sorted(REQUIRED):
        if not (ROOT / required).exists():
            errors.append(f"missing required document: {required}")

    markdown = sorted(ROOT.rglob("*.md"))
    for path in markdown:
        rel = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        if not text.strip():
            errors.append(f"empty Markdown document: {rel}")
            continue
        # Historical upgrade/prompt artifacts are provenance records. Their
        # embedded paths may intentionally describe a previous repository
        # layout, but the files themselves must remain present and non-empty.
        if rel.startswith(ARCHIVE_PREFIXES):
            continue
        for raw in LINK_RE.findall(strip_fenced_code(text)):
            target = local_target(path, raw)
            if target is None:
                continue
            try:
                target.relative_to(ROOT.resolve())
            except ValueError:
                errors.append(f"link escapes repository: {rel} -> {raw}")
                continue
            if not target.exists():
                errors.append(f"broken local link: {rel} -> {raw}")

    if errors:
        print("Documentation validation failed:")
        for error in errors:
            print(f" - {error}")
        return 1
    print(f"Documentation validation passed: {len(markdown)} Markdown files inventoried.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
''',
    )


def docs_index() -> None:
    write(
        "docs/README.md",
        '''# ZCoder Documentation

This directory is the navigation root for architecture, security, compliance, operations, enterprise behavior, guides, historical upgrade evidence, and archived implementation prompts. The authoritative package layout is `src/zcoder/`; root-level architecture/security/contribution documents remain the project policy source of truth.

## Current documentation

| Area | Entry point | Scope |
| --- | --- | --- |
| Architecture | [architecture/README.md](architecture/README.md) | Runtime boundaries, data flow, HA |
| Security | [security/README.md](security/README.md) | Identity, keys, encryption, SSO/SCIM |
| Compliance | [compliance/README.md](compliance/README.md) | Audit, retention, residency, policy, controls |
| Operations | [operations/README.md](operations/README.md) | Deployment, SLO, DR, observability, runbooks |
| Enterprise | [enterprise/README.md](enterprise/README.md) | RBAC, organizations, enterprise conformance |
| Guides | [guides/README.md](guides/README.md) | Operator/developer feature guides |
| Upgrade archive | [upgrades/README.md](upgrades/README.md) | Historical release and audit records |
| Prompt archive | [prompts/README.md](prompts/README.md) | Historical implementation/audit prompts |

## Repository policy documents

- [README](../README.md)
- [Architecture](../ARCHITECTURE.md)
- [Security policy](../SECURITY.md)
- [Contributing](../CONTRIBUTING.md)
- [Governance](../GOVERNANCE.md)
- [Support](../SUPPORT.md)
- [Roadmap](../ROADMAP.md)
- [Changelog](../CHANGELOG.md)

## Archive policy

`docs/upgrades/` and `docs/prompts/` are provenance archives. Text inside an archived record may refer to module names, test paths, or commands that were correct when that record was written. Current implementation guidance must come from root policy docs and current category docs. The documentation workflow inventories every Markdown file for non-empty content and validates local links on the active documentation surface.
''',
    )


def main() -> None:
    create_security_helpers()
    harden_network_calls()
    harden_shell_calls()
    harden_generated_code()
    harden_temp_paths()
    harden_sql()
    update_dependencies()
    github_files()
    workflows()
    documentation_files()
    docs_index()
    update_active_markdown_paths()
    docs_checker()
    print("Repository hardening migration applied.")


if __name__ == "__main__":
    main()
