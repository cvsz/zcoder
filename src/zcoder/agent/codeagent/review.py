"""UltraReview — deep multi-agent code review (Claude Code /code-review ultra port).

Runs multiple independent reviewer agents over a git diff in parallel, then a
verifier agent checks each finding. Only verified, deduplicated findings are
reported. Entirely local — no cloud, no hosted inference.
"""

from __future__ import annotations

import asyncio
import re
import subprocess  # nosec
from dataclasses import dataclass
from typing import Any

from zcoder.agent.codeagent.llm import LLM
from zcoder.agent.codeagent.loop import CodeAgent
from zcoder.agent.codeagent.permissions import Mode, PermissionPolicy
from zcoder.agent.codeagent.sessions import SessionStore
from zcoder.agent.codeagent.workspace import Workspace

REVIEWER_COUNT = 3
MAX_FILES = 500
MAX_LINES = 8000

REVIEWER_PROMPT = """You are a senior staff engineer doing a deep code review. Your ONLY job is to find REAL BUGS in the changes below.

Report ONLY:
- Logic errors (wrong conditions, off-by-one, incorrect variable use)
- Null/undefined dereferences
- Resource leaks (files, connections, locks not closed)
- Race conditions and concurrency bugs
- Security issues (injection, auth bypass, hardcoded secrets)
- Incorrect error handling (swallowed exceptions, missing checks)
- API misuse (wrong arguments, wrong return handling)

Do NOT report:
- Style, formatting, naming, or cosmetic issues
- Missing comments or documentation
- Type annotations or lack thereof
- Code organization preferences

For each finding, give: path:line — description
Be specific and cite exact code. If no bugs found, say 'No bugs found.'"""

VERIFIER_PROMPT = """You are a verification engineer. You will be given a claimed bug finding from a code review and the relevant code. Your job is to independently verify whether the bug is REAL.

Check:
1. Does the bug actually exist in the code as shown?
2. Is the finding accurate about file, line, and the problematic code?
3. Is it a real bug (not a false positive, not style, not a design choice)?

Respond with exactly: VERIFIED or REJECTED, followed by a one-sentence reason.

If REJECTED, explain why the finding is wrong."""


@dataclass
class ReviewFinding:
    file: str
    line: int | None
    description: str
    severity: str  # high | medium | low
    reviewer_id: str
    verified: bool = False
    verify_reason: str = ""


@dataclass
class ReviewerResult:
    reviewer_id: str
    findings: list[ReviewFinding]


def _git(ws: Workspace, *args: str) -> str:
    try:
        r = subprocess.run(  # nosec
            ["git", *args], cwd=ws.root, capture_output=True, text=True, timeout=15, check=False
        )
        if r.returncode != 0:
            return ""
        return r.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def get_default_branch(ws: Workspace) -> str:
    """Return the default branch (main or master), falling back to origin/HEAD."""
    for b in ("main", "master"):
        out = _git(ws, "rev-parse", "--verify", f"refs/heads/{b}")
        if out:
            return b
    out = _git(ws, "symbolic-ref", "refs/remotes/origin/HEAD")
    if out:
        m = re.search(r"refs/remotes/origin/(\S+)", out)
        if m:
            return m.group(1)
    return "main"


def get_diff(ws: Workspace, base: str | None = None) -> tuple[str, int, int]:
    """Return (diff_text, file_count, changed_lines) against ``base``."""
    base = base or get_default_branch(ws)
    # Ensure the base ref exists locally
    _git(ws, "fetch", "origin", base, "--depth=1")
    # Diff between base commit and working tree (includes staged + unstaged)
    diff = _git(ws, "diff", base, "--", ".")
    if not diff:
        return "", 0, 0
    files: set[str] = set()
    changed = 0
    for line in diff.splitlines():
        if line.startswith("diff --git"):
            m = re.search(r" b/(.+)$", line)
            if m:
                files.add(m.group(1))
        elif line.startswith(("+", "-")) and not line.startswith(("+++", "---")):
            changed += 1
    return diff, len(files), changed


def check_limits(file_count: int, line_count: int) -> str | None:
    """Return an error message if the diff exceeds limits, else None."""
    if file_count > MAX_FILES:
        return f"Diff too large: {file_count} files (max {MAX_FILES}). Use PR review instead."
    if line_count > MAX_LINES:
        return f"Diff too large: {line_count} changed lines (max {MAX_LINES}). Use PR review instead."
    return None


_FILE_LINE_RX = re.compile(r"^([\w./\\-]+\.\w+):(\d+)\s*[:\-—]\s*(.+)$", re.MULTILINE)
_FILE_ONLY_RX = re.compile(r"^([\w./\\-]+\.\w+)\s*[:\-—]\s*(.+)$", re.MULTILINE)


def _extract_findings(text: str, reviewer_id: str) -> list[ReviewFinding]:
    """Parse review findings from reviewer output."""
    findings: list[ReviewFinding] = []
    claimed_lines: set[int] = set()
    for m in _FILE_LINE_RX.finditer(text):
        start = m.start()
        claimed_lines.add(start)
        findings.append(
            ReviewFinding(
                file=m.group(1),
                line=int(m.group(2)),
                description=m.group(3).strip(),
                severity="medium",
                reviewer_id=reviewer_id,
            )
        )
    for m in _FILE_ONLY_RX.finditer(text):
        if m.start() in claimed_lines:
            continue
        already = any(f.file == m.group(1) and f.description == m.group(2).strip() for f in findings)
        if not already:
            findings.append(
                ReviewFinding(
                    file=m.group(1),
                    line=None,
                    description=m.group(2).strip(),
                    severity="medium",
                    reviewer_id=reviewer_id,
                )
            )
    return findings


def _dedupe(findings: list[ReviewFinding]) -> list[ReviewFinding]:
    """Merge findings that refer to the same file, line, and similar description."""
    merged: list[ReviewFinding] = []
    seen: set[tuple[str, int | str | None, str]] = set()
    for f in findings:
        key = (f.file, f.line, f.description[:60].lower())
        if key in seen:
            continue
        seen.add(key)
        merged.append(f)
    return merged


def _collect_text(events: list[Any]) -> str:
    """Concatenate text from TextDelta/Notice events."""
    parts: list[str] = []
    for ev in events:
        text = getattr(ev, "text", None)
        if isinstance(text, str) and text:
            parts.append(text)
    return "".join(parts)


class ReviewerAgent:
    """A single independent reviewer agent."""

    def __init__(self, reviewer_id: str, llm: LLM, ws: Workspace, policy: PermissionPolicy):
        self.reviewer_id = reviewer_id
        self.llm = llm
        self.ws = ws
        self.policy = policy

    async def review(self, diff: str, base: str) -> ReviewerResult:
        agent = CodeAgent(
            self.llm,
            self.ws,
            policy=self.policy,
            store=SessionStore(),
            memory=[],
            context_window=32768,
            max_steps=10,
        )
        prompt = (
            f"{REVIEWER_PROMPT}\n\n"
            f"Base branch: {base}\n"
            f"Diff (unified):\n```diff\n{diff}\n```\n\n"
            "Report each finding as: path:line — description\n"
            "If no bugs found, say 'No bugs found.'"
        )
        events = [e async for e in agent.run(prompt)]
        text = _collect_text(events)
        findings = _extract_findings(text, self.reviewer_id)
        return ReviewerResult(reviewer_id=self.reviewer_id, findings=findings)


class VerifierAgent:
    """Verifies each finding independently."""

    def __init__(self, llm: LLM, ws: Workspace, policy: PermissionPolicy):
        self.llm = llm
        self.ws = ws
        self.policy = policy

    async def verify(self, finding: ReviewFinding, base: str) -> ReviewFinding:
        agent = CodeAgent(
            self.llm,
            self.ws,
            policy=self.policy,
            store=SessionStore(),
            memory=[],
            context_window=32768,
            max_steps=5,
        )
        file_content = ""
        if finding.file:
            try:
                p = self.ws.resolve(finding.file)
                if p.exists():
                    file_content = p.read_text(encoding="utf-8", errors="replace")[:5000]
            except Exception:
                file_content = f"(could not read {finding.file})"
        prompt = (
            f"{VERIFIER_PROMPT}\n\n"
            f"Claimed finding: {finding.file}:{finding.line or '?'} — {finding.description}\n"
            f"Base branch: {base}\n"
            f"File content (first 5000 chars):\n```\n{file_content}\n```\n\n"
            "Respond with exactly: VERIFIED or REJECTED, followed by a one-sentence reason."
        )
        events = [e async for e in agent.run(prompt)]
        text = _collect_text(events).strip()
        verified = text.upper().startswith("VERIFIED")
        finding.verified = verified
        finding.verify_reason = text
        return finding


class UltraReview:
    """Orchestrates multiple reviewers and a verifier for deep code review."""

    def __init__(self, ws: Workspace, llm: LLM, reviewers: int = REVIEWER_COUNT):
        self.ws = ws
        self.llm = llm
        self.reviewers = reviewers
        self.policy = PermissionPolicy(workspace=ws)
        self.policy.set_mode(Mode.DEFAULT)

    async def run(self, base: str | None = None, note: str = "") -> dict[str, Any]:
        base = base or get_default_branch(self.ws)
        diff, file_count, line_count = get_diff(self.ws, base)

        if not diff:
            return {
                "status": "empty",
                "message": f"No changes to review against {base}.",
                "findings": [],
            }

        limit_err = check_limits(file_count, line_count)
        if limit_err:
            return {
                "status": "too_large",
                "message": limit_err,
                "findings": [],
                "files": file_count,
                "lines": line_count,
            }

        agents = [
            ReviewerAgent(f"reviewer-{i}", self.llm, self.ws, self.policy) for i in range(self.reviewers)
        ]
        results = await asyncio.gather(*(a.review(diff, base) for a in agents), return_exceptions=True)

        all_findings: list[ReviewFinding] = []
        for r in results:
            if isinstance(r, BaseException):
                continue
            all_findings.extend(r.findings)

        all_findings = _dedupe(all_findings)

        verifier = VerifierAgent(self.llm, self.ws, self.policy)
        verified_findings: list[ReviewFinding] = []
        for f in all_findings:
            try:
                await verifier.verify(f, base)
                if f.verified:
                    verified_findings.append(f)
            except Exception:  # nosec
                continue

        sev_order = {"high": 0, "medium": 1, "low": 2}
        verified_findings.sort(key=lambda f: (sev_order.get(f.severity, 9), f.file, f.line or 0))

        return {
            "status": "complete",
            "base": base,
            "files": file_count,
            "lines": line_count,
            "reviewers": self.reviewers,
            "findings_raw": len(all_findings),
            "findings_verified": len(verified_findings),
            "findings": verified_findings,
            "note": note,
        }


def format_review(result: dict[str, Any]) -> str:
    """Format review results for display."""
    if result["status"] == "empty":
        return result["message"]
    if result["status"] == "too_large":
        return result["message"]

    lines = [
        f"UltraReview complete — base: {result['base']}",
        f"Files: {result['files']} · Changed lines: {result['lines']} · "
        f"Reviewers: {result['reviewers']} · Raw findings: {result['findings_raw']} · "
        f"Verified: {result['findings_verified']}",
        "",
    ]
    if not result["findings"]:
        lines.append("No verified bugs found.")
        return "\n".join(lines)

    lines.append("## Verified findings")
    lines.append("")
    for i, f in enumerate(result["findings"], 1):
        loc = f"{f.file}:{f.line}" if f.line else f.file
        lines.append(f"{i}. [{f.severity}] {loc} — {f.description}")
        lines.append(f"   Verifier: {f.verify_reason}")
        lines.append("")
    return "\n".join(lines)
