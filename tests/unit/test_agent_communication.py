"""Tests for the Phase 17 agent communication module.

All persistence in these tests is hermetic: every AgentRegistry/TaskOffloader
is backed by a tmp_path file, so the developer's ~/.zcoder directory is never
touched and the suite is fully idempotent.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from zcoder.agent.communication import (
    MessageType,
    Operation,
    ProtocolError,
    RPCError,
    RPCNotification,
    RPCRequest,
    RPCResponse,
    create_error,
    create_notification,
    create_request,
    create_response,
    parse_message,
)
from zcoder.agent.communication.offloader import TaskOffloader, TaskState
from zcoder.agent.communication.registry import AgentInfo, AgentRegistry


@pytest.fixture()
def registry_path(tmp_path: Path) -> Path:
    return tmp_path / "agents.json"


@pytest.fixture()
def tasks_path(tmp_path: Path) -> Path:
    return tmp_path / "offloaded_tasks.json"


@pytest.fixture()
def registry(registry_path: Path) -> AgentRegistry:
    return AgentRegistry(storage_path=registry_path)


@pytest.fixture()
def offloader(tasks_path: Path) -> TaskOffloader:
    return TaskOffloader("agent-src", storage_path=tasks_path)


def _info(agent_id: str, *, capabilities=None, tags=None) -> AgentInfo:
    return AgentInfo(
        agent_id=agent_id,
        name=f"Agent {agent_id}",
        capabilities=capabilities if capabilities is not None else {},
        tags=tags if tags is not None else [],
        endpoint="http://127.0.0.1:9000",
    )


class TestProtocol:
    def test_create_request(self):
        msg = create_request("discover", {"capability": "test"}, "test-id")
        assert isinstance(msg, RPCRequest)
        assert msg.jsonrpc == "2.0"
        assert msg.id == "test-id"
        assert msg.method == "discover"
        assert msg.params == {"capability": "test"}
        assert msg.type == MessageType.REQUEST

    def test_create_request_auto_id(self):
        msg = create_request("discover", {"capability": "test"})
        assert msg.id is not None and len(msg.id) > 0

    def test_create_request_rejects_empty_method(self):
        with pytest.raises(ProtocolError):
            create_request("")

    def test_create_response(self):
        msg = create_response({"result": "ok"}, message_id="test-id")
        assert isinstance(msg, RPCResponse)
        assert msg.type == MessageType.RESPONSE
        assert msg.result == {"result": "ok"}

    def test_create_response_rejects_result_and_error(self):
        with pytest.raises(ProtocolError):
            create_response(result="ok", error={"code": -32601, "message": "x"})

    def test_create_notification(self):
        msg = create_notification("sync_state", {"state": "active"})
        assert isinstance(msg, RPCNotification)
        assert msg.id is None
        assert msg.method == "sync_state"
        assert msg.type == MessageType.NOTIFICATION

    def test_create_error(self):
        msg = create_error(-32601, "Method not found", data={"detail": "test"}, message_id="rid")
        assert isinstance(msg, RPCError)
        assert msg.type == MessageType.ERROR
        assert msg.error == {"code": -32601, "message": "Method not found", "data": {"detail": "test"}}

    def test_parse_request(self):
        msg = parse_message({"jsonrpc": "2.0", "id": "1", "method": "discover", "params": {}})
        assert isinstance(msg, RPCRequest)
        assert msg.type == MessageType.REQUEST
        assert msg.id == "1"
        assert msg.method == "discover"

    def test_parse_response(self):
        msg = parse_message({"jsonrpc": "2.0", "id": "1", "result": {"status": "ok"}})
        assert isinstance(msg, RPCResponse)
        assert msg.type == MessageType.RESPONSE
        assert msg.result == {"status": "ok"}

    def test_parse_notification(self):
        msg = parse_message({"jsonrpc": "2.0", "method": "sync_state", "params": {"state": "active"}})
        assert isinstance(msg, RPCNotification)
        assert msg.type == MessageType.NOTIFICATION
        assert msg.id is None

    def test_parse_error(self):
        msg = parse_message({"jsonrpc": "2.0", "id": "1", "error": {"code": -32601, "message": "Not found"}})
        assert isinstance(msg, RPCError)
        assert msg.type == MessageType.ERROR
        assert msg.error["code"] == -32601

    def test_parse_from_json_string_roundtrip(self):
        original = create_request("offload", {"task": "analyze"}, "rid-42")
        restored = parse_message(original.to_json())
        assert restored.id == "rid-42"
        assert restored.method == "offload"
        assert restored.params == {"task": "analyze"}
        assert restored.type == MessageType.REQUEST

    def test_to_json_is_valid_jsonrpc(self):
        msg = create_request("discover", {"capability": "test"}, "test-id")
        payload = json.loads(msg.to_json())
        assert payload["jsonrpc"] == "2.0"
        assert payload["type"] == "request"
        assert payload["method"] == "discover"

    def test_model_dump_json_alias(self):
        msg = create_request("discover", {"capability": "test"}, "test-id")
        assert msg.model_dump_json() == msg.to_json()

    def test_parse_rejects_bad_version(self):
        with pytest.raises(ProtocolError):
            parse_message({"jsonrpc": "1.0", "id": "1", "method": "x"})

    def test_parse_rejects_invalid_json(self):
        with pytest.raises(ProtocolError):
            parse_message("{not json")

    def test_parse_rejects_non_object(self):
        with pytest.raises(ProtocolError):
            parse_message("[1,2,3]")


class TestAgentRegistry:
    def test_register_and_get(self, registry):
        registry.register_agent(_info("a1", capabilities={"compute": True}, tags=["worker"]))
        got = registry.get_agent("a1")
        assert got is not None
        assert got.name == "Agent a1"
        assert got.capabilities == {"compute": True}
        assert got.tags == ["worker"]

    def test_get_missing_returns_none(self, registry):
        assert registry.get_agent("nope") is None

    def test_unregister(self, registry):
        registry.register_agent(_info("a1"))
        assert registry.unregister_agent("a1") is True
        assert registry.get_agent("a1") is None
        assert registry.unregister_agent("a1") is False

    def test_list_agents(self, registry):
        for i in range(3):
            registry.register_agent(_info(f"a-{i}"))
        assert len(registry.list_agents()) == 3

    def test_list_agents_skips_corrupt_entries(self, registry_path):
        registry_path.write_text(
            json.dumps(
                {
                    "good": {
                        "name": "G",
                        "capabilities": {"x": True},
                        "endpoint": "",
                        "last_seen": 1.0,
                        "tags": [],
                    },
                    "bad": "not-a-mapping",
                }
            )
        )
        reg = AgentRegistry(storage_path=registry_path)
        assert [a.agent_id for a in reg.list_agents()] == ["good"]

    def test_corrupt_file_quarantined(self, registry_path):
        registry_path.write_text("{ not json")
        reg = AgentRegistry(storage_path=registry_path)
        assert reg.list_agents() == []
        assert registry_path.with_suffix(registry_path.suffix + ".corrupt").exists()
        assert not registry_path.exists()

    def test_persistence_roundtrip(self, registry_path):
        reg = AgentRegistry(storage_path=registry_path)
        reg.register_agent(_info("a1", capabilities={"compute": True}))
        reg2 = AgentRegistry(storage_path=registry_path)
        got = reg2.get_agent("a1")
        assert got is not None and got.capabilities == {"compute": True}

    def test_find_by_capability_exact(self, registry):
        registry.register_agent(_info("a1", capabilities={"compute": True, "test": True}))
        registry.register_agent(_info("a2", capabilities={"test": True}))
        registry.register_agent(_info("a3", capabilities={"compute": False}))
        found = registry.find_agents_by_capability("compute")
        assert [a.agent_id for a in found] == ["a1"]

    def test_find_by_capability_case_insensitive(self, registry):
        registry.register_agent(_info("a1", capabilities={"Compute": True}))
        assert [a.agent_id for a in registry.find_agents_by_capability("COMPUTE")] == ["a1"]

    def test_find_by_capability_and_tag(self, registry):
        registry.register_agent(_info("a1", capabilities={"compute": True}, tags=["us-east"]))
        registry.register_agent(_info("a2", capabilities={"compute": True}, tags=["us-west"]))
        east = registry.find_agents_by_capability("compute", tag="us-east")
        assert [a.agent_id for a in east] == ["a1"]

    def test_search_agents(self, registry):
        registry.register_agent(_info("a1", tags=["worker", "us-east"]))
        registry.register_agent(_info("a2", tags=["coordinator"]))
        found = registry.search_agents("worker")
        assert "a1" in {a.agent_id for a in found}
        assert "a2" not in {a.agent_id for a in found}

    def test_search_by_capability_key(self, registry):
        registry.register_agent(_info("a1", capabilities={"image_gen": True}))
        found = registry.search_agents("image_gen", search_in=["capabilities"])
        assert [a.agent_id for a in found] == ["a1"]

    def test_list_capabilities(self, registry):
        caps = registry.search_agents("zznocapacityzz")
        assert caps == []

    def test_heartbeat_updates_last_seen(self, registry):
        registry.register_agent(_info("a1"))
        before = registry.get_agent("a1").last_seen
        import time

        time.sleep(0.01)
        registry.heartbeat("a1")
        assert registry.get_agent("a1").last_seen > before

    def test_heartbeat_missing(self, registry):
        assert registry.heartbeat("nope") is None

    def test_clear(self, registry):
        registry.register_agent(_info("a1"))
        registry.clear()
        assert registry.list_agents() == []
        assert json.loads(registry.path.read_text()) == {}

    def test_validation_rejects_empty_id(self):
        with pytest.raises(ValueError):
            AgentInfo(agent_id="", name="x")

    def test_validation_rejects_empty_name(self):
        with pytest.raises(ValueError):
            AgentInfo(agent_id="a", name="  ")

    def test_legacy_list_capabilities_normalized(self):
        info = AgentInfo(agent_id="a", name="n", capabilities=["x", "y"], tags=[])
        assert info.capabilities == {"x": True, "y": True}

    def test_legacy_dict_tags_normalized(self):
        info = AgentInfo(agent_id="a", name="n", capabilities={}, tags={"role": "worker"})
        assert info.tags == ["role"]


class TestTaskOffloader:
    def test_offload_task(self, offloader):
        task_id = offloader.offload_task("agent-dst", Operation.OFFLOAD, {"data": "test"})
        assert task_id
        status = offloader.get_task_status(task_id)
        assert status["state"] == "pending"
        assert status["source_agent"] == "agent-src"
        assert status["target_agent"] == "agent-dst"
        assert status["operation"] == "offload"

    def test_get_status_unknown(self, offloader):
        assert "error" in offloader.get_task_status("nope")

    def test_offload_rejects_bad_timeout(self, offloader):
        with pytest.raises(ValueError):
            offloader.offload_task("agent-dst", Operation.OFFLOAD, {}, timeout=0)

    def test_offload_rejects_empty_target(self, offloader):
        with pytest.raises(ValueError):
            offloader.offload_task("  ", Operation.OFFLOAD, {})

    def test_mark_in_progress(self, offloader):
        task_id = offloader.offload_task("agent-dst", Operation.OFFLOAD, {})
        assert offloader.mark_in_progress(task_id) is True
        assert offloader.get_task_status(task_id)["state"] == "in_progress"
        assert offloader.mark_in_progress(task_id) is False

    def test_cancel_task(self, offloader):
        task_id = offloader.offload_task("agent-dst", Operation.OFFLOAD, {})
        assert offloader.cancel_task(task_id) is True
        assert offloader.get_task_status(task_id)["state"] == "cancelled"
        assert offloader.cancel_task(task_id) is False

    def test_complete_task(self, offloader):
        task_id = offloader.offload_task("agent-dst", Operation.OFFLOAD, {})
        assert offloader.complete_task(task_id, result={"out": "done"}) is True
        assert offloader.get_task_status(task_id)["state"] == "completed"
        assert offloader.get_task_status(task_id)["result"] == {"out": "done"}
        assert offloader.complete_task(task_id, result={}) is False

    def test_fail_task(self, offloader):
        task_id = offloader.offload_task("agent-dst", Operation.OFFLOAD, {})
        assert offloader.fail_task(task_id, "boom") is True
        status = offloader.get_task_status(task_id)
        assert status["state"] == "failed"
        assert status["error"] == "boom"

    def test_expire_stale(self, offloader):
        task_id = offloader.offload_task("agent-dst", Operation.OFFLOAD, {}, timeout=10.0)
        far_future = __import__("time").time() + 60
        assert offloader.expire_stale(now=far_future) == [task_id]
        assert offloader.get_task_status(task_id)["state"] == "failed"

    def test_expire_stale_keeps_fresh(self, offloader):
        task_id = offloader.offload_task("agent-dst", Operation.OFFLOAD, {}, timeout=10.0)
        assert offloader.expire_stale() == []
        assert offloader.get_task_status(task_id)["state"] == "pending"

    def test_persistence_roundtrip(self, tasks_path):
        off = TaskOffloader("agent-src", storage_path=tasks_path)
        task_id = off.offload_task("agent-dst", Operation.OFFLOAD, {"x": 1})
        off2 = TaskOffloader("agent-src", storage_path=tasks_path)
        status = off2.get_task_status(task_id)
        assert status["state"] == "pending"
        assert status["params"] == {"x": 1}

    def test_corrupt_task_store_quarantined(self, tasks_path):
        tasks_path.write_text("{ not json")
        off = TaskOffloader("agent-src", storage_path=tasks_path)
        assert off.list_tasks() == []
        assert tasks_path.with_suffix(tasks_path.suffix + ".corrupt").exists()

    def test_list_tasks_filter(self, offloader):
        t1 = offloader.offload_task("agent-dst", Operation.OFFLOAD, {})
        offloader.offload_task("agent-dst", Operation.OFFLOAD, {})
        offloader.complete_task(t1, result="ok")
        assert len(offloader.list_tasks()) == 2
        assert len(offloader.list_tasks(TaskState.COMPLETED)) == 1
        assert len(offloader.list_tasks(TaskState.PENDING)) == 1

    def test_max_tasks_eviction(self, tasks_path):
        off = TaskOffloader("agent-src", storage_path=tasks_path, max_tasks=2)
        for _ in range(4):
            off.offload_task("agent-dst", Operation.OFFLOAD, {})
        off.complete_task(next(iter(off._tasks)), result="ok")
        off.offload_task("agent-dst", Operation.OFFLOAD, {})
        assert len(off.list_tasks()) <= 4

    def test_empty_agent_id_rejected(self, tasks_path):
        with pytest.raises(ValueError):
            TaskOffloader("", storage_path=tasks_path)


class TestConsensus:
    def test_propose_and_vote_messages(self, offloader):
        propose = offloader.build_propose_message("p1", {"change": "deploy"})
        assert isinstance(propose, RPCRequest)
        assert propose.method == "propose"
        assert propose.params["proposal_id"] == "p1"

        vote = offloader.build_vote_message("p1", True, voter="peer-1")
        assert vote.method == "vote"
        assert vote.params == {"proposal_id": "p1", "vote": True, "voter": "peer-1"}

        accept = offloader.build_accept_message("p1")
        assert isinstance(accept, RPCNotification)
        assert accept.method == "accept"

        reject = offloader.build_reject_message("p1", "not ready")
        assert reject.method == "reject"
        assert reject.params["reason"] == "not ready"

    def test_await_approval_quorum(self, offloader):
        approved, reason = offloader.await_approval("p1", {"a": True, "b": True, "c": False})
        assert approved is True and "accepted" in reason
        rejected, reason = offloader.await_approval("p1", {"a": False, "b": False, "c": True})
        assert rejected is False and "rejected" in reason
        none, reason = offloader.await_approval("p1", {})
        assert none is False and reason == "no votes collected"
        pending, reason = offloader.await_approval("p1", {"a": True, "b": False}, quorum=2)
        assert pending is False and "inconclusive" in reason

    def test_share_and_sync_session_offloaded(self, offloader):
        t1 = offloader.share_session("s1", {"history": "h"}, "agent-dst")
        t2 = offloader.sync_state("s1", {"cursor": 10}, "agent-dst")
        assert offloader.get_task_status(t1)["operation"] == "share_session"
        assert offloader.get_task_status(t2)["operation"] == "sync_state"


class TestIntegration:
    def test_full_communication_flow(self, registry_path, tasks_path):
        reg = AgentRegistry(storage_path=registry_path)
        reg.register_agent(_info("coordinator", capabilities={"coordinate": True}, tags=["coordinator"]))
        reg.register_agent(_info("worker", capabilities={"compute": True}, tags=["worker"]))

        workers = reg.find_agents_by_capability("compute")
        assert [a.agent_id for a in workers] == ["worker"]

        off = TaskOffloader("coordinator", storage_path=tasks_path)
        task_id = off.offload_task("worker", Operation.OFFLOAD, {"input": "data"})
        assert off.get_task_status(task_id)["state"] == "pending"
        off.mark_in_progress(task_id)
        off.complete_task(task_id, result={"output": "processed"})
        status = off.get_task_status(task_id)
        assert status["state"] == "completed"
        assert status["result"] == {"output": "processed"}
