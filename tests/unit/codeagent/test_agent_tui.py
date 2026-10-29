from __future__ import annotations

import pytest

pytest.importorskip("textual")

from textual.widgets import Input, Static  # noqa: E402

from tests.unit.codeagent.conftest import FakeLLM  # noqa: E402
from zcoder.agent.codeagent.llm import LLMError  # noqa: E402
from zcoder.agent.codeagent.loop import CodeAgent  # noqa: E402
from zcoder.agent.codeagent.permissions import Mode, PermissionPolicy  # noqa: E402
from zcoder.agent.codeagent.sessions import SessionStore  # noqa: E402
from zcoder.agent.codeagent.workspace import Workspace  # noqa: E402
from zcoder.interfaces.cli import agent_tui as tui  # noqa: E402


def make_app(tmp_path, script):
    ws = Workspace(tmp_path)
    agent = CodeAgent(
        FakeLLM(script),
        ws,
        policy=PermissionPolicy(workspace=ws),
        store=SessionStore(tmp_path / "sess"),
        memory=[],
        retry_delays=(0.0,),
    )
    return tui.AgentTUI(agent)


async def settle(app, pilot):
    await pilot.pause()
    await app.workers.wait_for_complete()
    await pilot.pause()


async def send(app, pilot, text):
    box = app.query_one("#prompt", Input)
    box.value = text
    box.focus()
    await pilot.press("enter")


def texts(app):
    out = []
    for w in app.query(Static):
        r = w.render() if hasattr(w, "render") else ""
        out.append(str(getattr(r, "plain", r)))
    return "\n".join(out)


async def test_streams_assistant_reply(tmp_path):
    app = make_app(tmp_path, [{"chunks": ["Hello ", "**world**"]}])
    async with app.run_test(size=(120, 40)) as pilot:
        await send(app, pilot, "hi")
        await settle(app, pilot)
        assert [m.text for m in app.query(tui.AssistantMessage)] == ["Hello **world**"]
        assert "❯ hi" in texts(app)
        assert not app.busy


async def test_permission_dialog_allows_edit(tmp_path):
    app = make_app(
        tmp_path, [{"calls": [("Write", {"path": "n.py", "content": "x = 1\n"})]}, {"text": "done"}]
    )
    async with app.run_test(size=(120, 40)) as pilot:
        await send(app, pilot, "make n.py")
        for _ in range(50):
            await pilot.pause()
            if isinstance(app.screen, tui.PermissionScreen):
                break
        assert isinstance(app.screen, tui.PermissionScreen)
        assert app.screen.request.tool == "Write" and "+x = 1" in app.screen.request.diff
        await pilot.press("y")
        await settle(app, pilot)
        assert (tmp_path / "n.py").read_text() == "x = 1\n"
        card = app.query(tui.ToolCard).first()
        assert "✓" in card.title and not card.collapsed  # diffs start expanded


async def test_permission_dialog_deny_with_feedback(tmp_path):
    app = make_app(tmp_path, [{"calls": [("Write", {"path": "n.py", "content": "x"})]}, {"text": "ok"}])
    async with app.run_test(size=(120, 40)) as pilot:
        await send(app, pilot, "go")
        for _ in range(50):
            await pilot.pause()
            if isinstance(app.screen, tui.PermissionScreen):
                break
        await pilot.press("f")
        await pilot.pause()
        fb = app.screen.query_one("#dlg-feedback", Input)
        fb.value = "use pathlib"
        await pilot.press("enter")
        await settle(app, pilot)
        assert not (tmp_path / "n.py").exists()
        card = app.query(tui.ToolCard).first()
        assert "✗" in card.title and "use pathlib" in str(card.body.render())


async def test_escape_denies(tmp_path):
    app = make_app(tmp_path, [{"calls": [("Bash", {"command": "mkdir x"})]}, {"text": "ok"}])
    async with app.run_test(size=(120, 40)) as pilot:
        await send(app, pilot, "go")
        for _ in range(50):
            await pilot.pause()
            if isinstance(app.screen, tui.PermissionScreen):
                break
        await pilot.press("escape")
        await settle(app, pilot)
        assert not (tmp_path / "x").exists()


async def test_slash_commands_and_clear(tmp_path):
    app = make_app(tmp_path, [{"text": "a"}])
    async with app.run_test(size=(120, 40)) as pilot:
        await send(app, pilot, "/help")
        await settle(app, pilot)
        assert "/compact" in texts(app)
        await send(app, pilot, "/bogus")
        await settle(app, pilot)
        assert "Unknown command" in texts(app)
        await send(app, pilot, "hello")
        await settle(app, pilot)
        assert len(app.agent.messages) == 2
        await send(app, pilot, "/clear")
        await settle(app, pilot)
        assert app.agent.messages == [] and not list(app.query(tui.AssistantMessage))


async def test_init_command_runs_a_model_turn(tmp_path):
    app = make_app(tmp_path, [{"text": "analysing"}])
    async with app.run_test(size=(120, 40)) as pilot:
        await send(app, pilot, "/init")
        await settle(app, pilot)
        assert "ZCODER.md" in app.agent.messages[0]["content"] and len(app.agent.messages) == 2


async def test_shift_tab_cycles_modes_and_updates_status(tmp_path):
    app = make_app(tmp_path, [])
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("shift+tab")
        assert app.agent.mode == Mode.ACCEPT_EDITS and "accept edits" in str(
            app.query_one("#status").render()
        )
        await pilot.press("shift+tab")
        assert app.agent.mode == Mode.PLAN


async def test_todo_panel_follows_agent(tmp_path):
    todos = [{"content": "write tests", "status": "in_progress"}, {"content": "ship", "status": "pending"}]
    app = make_app(tmp_path, [{"calls": [("TodoWrite", {"todos": todos})]}, {"text": "ok"}])
    async with app.run_test(size=(120, 40)) as pilot:
        await send(app, pilot, "plan")
        await settle(app, pilot)
        panel = app.query_one("#todos")
        assert panel.display and "◐ write tests" in str(panel.render())
        await pilot.press("ctrl+t")
        assert not panel.display


async def test_llm_failure_is_shown_not_fatal(tmp_path):
    app = make_app(tmp_path, [LLMError("server down")])
    async with app.run_test(size=(120, 40)) as pilot:
        await send(app, pilot, "go")
        await settle(app, pilot)
        assert "server down" in texts(app) and not app.busy
        await send(app, pilot, "/status")
        await settle(app, pilot)
        assert "Session:" in texts(app)


async def test_history_navigation_and_persistence(tmp_path):
    app = make_app(tmp_path, [{"text": "1"}, {"text": "2"}])
    async with app.run_test(size=(120, 40)) as pilot:
        await send(app, pilot, "first")
        await settle(app, pilot)
        await send(app, pilot, "second")
        await settle(app, pilot)
        box = app.query_one("#prompt", tui.PromptInput)
        await pilot.press("up")
        assert box.value == "second"
        await pilot.press("up")
        assert box.value == "first"
        await pilot.press("down", "down")
        assert box.value == ""
    saved = (tmp_path / ".zhome" / "history").read_text().splitlines()
    assert saved == ["first", "second"]


async def test_busy_prompt_is_not_dropped(tmp_path):
    app = make_app(tmp_path, [{"text": "x"}])
    async with app.run_test(size=(120, 40)) as pilot:
        app.busy = True
        await send(app, pilot, "queued?")
        await pilot.pause()
        assert app.agent.messages == [] and "working" in texts(app)
        app.busy = False


async def test_resume_replays_history(tmp_path):
    first = make_app(tmp_path, [{"text": "the answer"}])
    async with first.run_test(size=(120, 40)) as pilot:
        await send(first, pilot, "question")
        await settle(first, pilot)
    sid = first.agent.session_id
    second = make_app(tmp_path, [])
    second.agent.store = first.agent.store
    second.agent.load_session(sid)
    async with second.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert "❯ question" in texts(second) and [m.text for m in second.query(tui.AssistantMessage)] == [
            "the answer"
        ]


async def test_suggester_completes_commands_and_files(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("")
    app = make_app(tmp_path, [])
    s = tui.AgentSuggester(app.agent)
    assert await s.get_suggestion("/com") == "/compact"
    assert await s.get_suggestion("/compact") is None
    assert await s.get_suggestion("explain @src/a") == "explain @src/app.py"
    assert await s.get_suggestion("mail me@src") is None
    assert await s.get_suggestion("plain text") is None


def test_pure_helpers():
    assert tui.describe_call("Bash", {"command": "ls -la\necho"}) == "ls -la"
    assert tui.describe_call("TodoWrite", {"todos": [1, 2]}) == "2 tasks"
    diff = tui.render_diff("--- a/x\n+++ b/x\n@@ -1 +1 @@\n-old\n+new\n ctx\n")
    styles = {diff.plain[sp.start : sp.end].rstrip("\n"): str(sp.style) for sp in diff.spans}
    assert styles["-old"] == "red" and styles["+new"] == "green" and styles["@@ -1 +1 @@"] == "cyan"
    assert "more lines" in tui.render_diff("+x\n" * 300, max_lines=10).plain
    # file content that looks like markup must never be interpreted
    assert tui.render_output("[bold]x[/bold]").plain == "[bold]x[/bold]"
    assert "+5 lines" in tui.render_output("\n".join("l" for _ in range(45))).plain
