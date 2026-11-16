"""Tests for UltraReview (Claude Code /code-review ultra port)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from zcoder.agent.codeagent.llm import LLMChunk
from zcoder.agent.codeagent.permissions import PermissionPolicy
from zcoder.agent.codeagent.review import (
    ReviewerAgent,
    ReviewFinding,
    UltraReview,
    VerifierAgent,
    _dedupe,
    _extract_findings,
    check_limits,
    format_review,
)
from zcoder.agent.codeagent.workspace import Workspace


def _make_git_repo(tmp_path: Path, branch: str = "main") -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "a@b"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    # Temp repo fixture is not about git signing; disable gpgsign so commits
    # succeed non-interactively in environments where commit.gpgsign is
    # globally enabled (e.g. with a passphrase-protected key and no tty).
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "commit", "--allow-empty", "-qm", "init"],
        cwd=tmp_path,
        check=True,
    )
    if branch != "main":
        subprocess.run(
            ["git", "symbolic-ref", "HEAD", f"refs/heads/{branch}"],
            cwd=tmp_path,
            check=False,
        )
    return tmp_path


class TestExtractFindings:
    def test_parse_file_line_description(self):
        text = "src/foo.py:42 — null dereference when x is None\nsrc/bar.py:10 — off-by-one in loop"
        findings = _extract_findings(text, "reviewer-0")
        assert len(findings) == 2
        assert findings[0].file == "src/foo.py"
        assert findings[0].line == 42
        assert "null dereference" in findings[0].description
        assert findings[0].reviewer_id == "reviewer-0"
        assert findings[1].file == "src/bar.py"
        assert findings[1].line == 10

    def test_parse_file_only(self):
        text = "src/foo.py — resource leak in file handle"
        findings = _extract_findings(text, "reviewer-0")
        assert len(findings) == 1
        assert findings[0].file == "src/foo.py"
        assert findings[0].line is None
        assert "resource leak" in findings[0].description

    def test_ignores_non_matching_lines(self):
        text = "Some intro text\nNo bugs found.\nAnother paragraph"
        findings = _extract_findings(text, "reviewer-0")
        assert findings == []

    def test_mixed_formats(self):
        text = (
            "src/a.py:5 — division by zero\n"
            "src/b.py — missing null check\n"
            "not a finding line\n"
            "src/c.py:100 — race condition on counter\n"
        )
        findings = _extract_findings(text, "r1")
        assert len(findings) == 3
        files_lines = [(f.file, f.line) for f in findings]
        assert ("src/a.py", 5) in files_lines
        assert ("src/b.py", None) in files_lines
        assert ("src/c.py", 100) in files_lines


class TestDedupe:
    def test_removes_exact_duplicates(self):
        findings = [
            ReviewFinding("src/foo.py", 42, "null deref", "medium", "r0"),
            ReviewFinding("src/foo.py", 42, "null deref", "medium", "r1"),
            ReviewFinding("src/bar.py", 10, "different bug", "medium", "r0"),
        ]
        result = _dedupe(findings)
        assert len(result) == 2
        files = sorted(f.file for f in result)
        assert files == ["src/bar.py", "src/foo.py"]

    def test_keeps_different_findings_same_file(self):
        findings = [
            ReviewFinding("src/foo.py", 42, "bug one", "medium", "r0"),
            ReviewFinding("src/foo.py", 42, "bug two", "medium", "r1"),
        ]
        result = _dedupe(findings)
        assert len(result) == 2

    def test_empty_list(self):
        assert _dedupe([]) == []


class TestCheckLimits:
    def test_within_limits(self):
        assert check_limits(100, 500) is None
        assert check_limits(500, 8000) is None

    def test_too_many_files(self):
        msg = check_limits(501, 100)
        assert msg is not None and "501" in msg and "files" in msg

    def test_too_many_lines(self):
        msg = check_limits(10, 8001)
        assert msg is not None and "8001" in msg and "lines" in msg


class FakeReviewLLM:
    """LLM that returns scripted review text (no tool calls)."""

    model = "fake-review-model"

    def __init__(self, script):
        self.script = list(script)
        self.requests: list[tuple[list, list]] = []

    async def stream(self, messages, tools):
        self.requests.append((list(messages), list(tools)))
        step = self.script.pop(0) if self.script else {"text": "done"}
        if isinstance(step, Exception):
            raise step
        for piece in step.get("chunks", [step["text"]] if step.get("text") else []):
            yield LLMChunk("text", text=piece)
        yield LLMChunk("usage", prompt_tokens=10, completion_tokens=5)
        yield LLMChunk("finish", finish_reason="stop")


class TestReviewerAgent:
    @pytest.mark.asyncio
    async def test_review_returns_findings(self, tmp_path):
        _make_git_repo(tmp_path)
        (tmp_path / "buggy.py").write_text("result = 1 / 0\n")
        subprocess.run(["git", "add", "buggy.py"], cwd=tmp_path, check=True)
        ws = Workspace(tmp_path)

        llm = FakeReviewLLM([{"text": "src/buggy.py:1 — division by zero will crash at runtime"}])
        policy = PermissionPolicy(workspace=ws)
        agent = ReviewerAgent("r0", llm, ws, policy)
        result = await agent.review("diff content", "main")

        assert len(result.findings) == 1
        assert result.findings[0].file == "src/buggy.py"
        assert result.findings[0].line == 1
        assert "division by zero" in result.findings[0].description

    @pytest.mark.asyncio
    async def test_review_no_findings(self, tmp_path):
        _make_git_repo(tmp_path)
        ws = Workspace(tmp_path)
        llm = FakeReviewLLM([{"text": "No bugs found."}])
        policy = PermissionPolicy(workspace=ws)
        agent = ReviewerAgent("r0", llm, ws, policy)
        result = await agent.review("diff content", "main")
        assert result.findings == []


class TestVerifierAgent:
    @pytest.mark.asyncio
    async def test_verify_accepts_real_bug(self, tmp_path):
        (tmp_path / "buggy.py").write_text("x = 1 / 0\n")
        ws = Workspace(tmp_path)
        llm = FakeReviewLLM([{"text": "VERIFIED — the division by zero is a real crash bug"}])
        policy = PermissionPolicy(workspace=ws)
        verifier = VerifierAgent(llm, ws, policy)
        finding = ReviewFinding("buggy.py", 1, "division by zero", "medium", "r0")
        result = await verifier.verify(finding, "main")
        assert result.verified is True
        assert "division by zero" in result.verify_reason

    @pytest.mark.asyncio
    async def test_verify_rejects_false_positive(self, tmp_path):
        (tmp_path / "fine.py").write_text("x = 1\n")
        ws = Workspace(tmp_path)
        llm = FakeReviewLLM([{"text": "REJECTED — this is intentional, not a bug"}])
        policy = PermissionPolicy(workspace=ws)
        verifier = VerifierAgent(llm, ws, policy)
        finding = ReviewFinding("fine.py", 1, "supposed bug", "medium", "r0")
        result = await verifier.verify(finding, "main")
        assert result.verified is False


class TestUltraReview:
    @pytest.mark.asyncio
    async def test_run_returns_empty_for_no_changes(self, tmp_path):
        _make_git_repo(tmp_path)
        ws = Workspace(tmp_path)
        llm = FakeReviewLLM([])
        review = UltraReview(ws, llm, reviewers=1)
        result = await review.run()
        assert result["status"] == "empty"
        assert "No changes" in result["message"]

    @pytest.mark.asyncio
    async def test_run_with_findings(self, tmp_path):
        _make_git_repo(tmp_path)
        (tmp_path / "buggy.py").write_text("result = 1 / 0\n")
        subprocess.run(["git", "add", "buggy.py"], cwd=tmp_path, check=True)
        ws = Workspace(tmp_path)

        llm = FakeReviewLLM(
            [
                {"text": "src/buggy.py:1 — division by zero will crash"},
                {"text": "VERIFIED — division by zero is a real crash bug"},
            ]
        )
        review = UltraReview(ws, llm, reviewers=1)
        result = await review.run()

        assert result["status"] == "complete"
        assert result["files"] >= 1


class TestFormatReview:
    def test_format_empty(self):
        result = {"status": "empty", "message": "No changes to review."}
        assert format_review(result) == "No changes to review."

    def test_format_too_large(self):
        result = {"status": "too_large", "message": "Diff too large: 600 files"}
        assert format_review(result) == "Diff too large: 600 files"

    def test_format_complete_no_findings(self):
        result = {
            "status": "complete",
            "base": "main",
            "files": 10,
            "lines": 50,
            "reviewers": 3,
            "findings_raw": 0,
            "findings_verified": 0,
            "findings": [],
            "note": "",
        }
        out = format_review(result)
        assert "UltraReview complete" in out
        assert "No verified bugs found." in out

    def test_format_complete_with_findings(self):
        result = {
            "status": "complete",
            "base": "main",
            "files": 10,
            "lines": 50,
            "reviewers": 3,
            "findings_raw": 2,
            "findings_verified": 1,
            "findings": [
                ReviewFinding(
                    "src/buggy.py",
                    42,
                    "division by zero",
                    "high",
                    "r0",
                    verified=True,
                    verify_reason="VERIFIED — real crash",
                )
            ],
            "note": "",
        }
        out = format_review(result)
        assert "Verified: 1" in out
        assert "src/buggy.py:42" in out
        assert "division by zero" in out
