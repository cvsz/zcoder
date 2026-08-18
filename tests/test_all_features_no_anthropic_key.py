"""Comprehensive test suite verifying all ZCoder features without requiring an Anthropic API Key."""

import os
import sys
import unittest
from pathlib import Path

# Ensure root src is in path
src_dir = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(src_dir))

from zcoder.api.public.v1 import PublicAPIV1Router  # noqa: E402
from zcoder.claude.personalities import PERSONALITIES  # noqa: E402
from zcoder.domain.models.tenant import EnterpriseRole, RequestContext  # noqa: E402
from zcoder.enterprise.local_ai_stack import (  # noqa: E402
    AutonomousEngineeringLoop,  # noqa: E402
    Checkpoint,  # noqa: E402
    CheckpointStore,  # noqa: E402
    EngineeringTask,  # noqa: E402
    HardwareProfiler,  # noqa: E402
    LocalRepositoryIndexer,  # noqa: E402
    OllamaAdapter,  # noqa: E402
    SecurityGate,  # noqa: E402
)  # noqa: E402
from zcoder.main import AGENT_SYSTEM_PROMPTS, _api_key  # noqa: E402


class TestZCoderFeaturesWithoutKey(unittest.TestCase):
    def setUp(self):
        # Enforce no Anthropic key / Local mode for THIS test class only, then
        # restore afterwards so the rest of the suite is not polluted.
        self._old_local_mode = os.environ.get("ZCODER_LOCAL_MODE")
        self._old_api_key = os.environ.get("ANTHROPIC_API_KEY")
        os.environ["ZCODER_LOCAL_MODE"] = "1"
        os.environ["ANTHROPIC_API_KEY"] = "local-mode-no-key-required"

    def tearDown(self):
        for name, old in (
            ("ZCODER_LOCAL_MODE", self._old_local_mode),
            ("ANTHROPIC_API_KEY", self._old_api_key),
        ):
            if old is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = old

    def test_01_api_key_guard_bypass(self):
        """Verify _api_key does not raise or exit when ZCODER_LOCAL_MODE=1."""

        class MockArgs:
            api_key = None

        key = _api_key(MockArgs())
        self.assertEqual(key, "local-mode-no-key-required")

    def test_02_personalities_and_agents_registry(self):
        """Verify all agent roles and personalities load offline without network."""
        self.assertGreaterEqual(len(PERSONALITIES), 5)
        self.assertIn("pragmatic", PERSONALITIES)
        self.assertIn("code_generator", AGENT_SYSTEM_PROMPTS)
        self.assertIn("security_auditor", AGENT_SYSTEM_PROMPTS)

    def test_03_hardware_profiler(self):
        """Verify local zero-cost hardware detection."""
        profile = HardwareProfiler.profile()
        self.assertIsNotNone(profile.os_name)
        self.assertGreater(profile.cpu_cores, 0)
        self.assertGreater(profile.ram_total_gb, 0.0)

    def test_04_local_repository_indexer(self):
        """Verify TF-IDF local repo indexer runs without external vector DB."""
        indexer = LocalRepositoryIndexer()
        indexed = indexer.index_file(
            "src/auth_service.py", "def authenticate_user(): pass\ndef check_permission(): pass"
        )
        self.assertTrue(indexed)
        results = indexer.search("authenticate_user", top_k=2)
        self.assertTrue(len(results) > 0)
        self.assertEqual(results[0][0], "src/auth_service.py")

    def test_05_security_gate(self):
        """Verify local automated security policy validator on diffs."""
        gate = SecurityGate()
        task = EngineeringTask(task_id="t1", project_id="p1", description="test task")

        # Clean diff
        clean_diff = ["+ def calculate_tax(subtotal):", "+     return subtotal * 0.07"]
        report_safe = gate.check(clean_diff, task)
        self.assertTrue(report_safe.passed)

        # Leak secret in diff
        leaky_diff = ["+ ANTHROPIC_API_KEY = 'sk-ant-api03-live-secret-leak'"]
        report_unsafe = gate.check(leaky_diff, task)
        self.assertFalse(report_unsafe.passed)

    def test_06_checkpoint_store(self):
        """Verify local resumable state & checkpoint engine."""
        store = CheckpointStore()
        cp = Checkpoint(
            checkpoint_id="cp_001",
            task_id="task_123",
            attempt_id="att_01",
            phase="PLAN",
            payload={"plan_ready": True},
        )
        store.save(cp)
        loaded = store.latest_for_task("task_123")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.phase, "PLAN")

    def test_07_public_api_v1_router(self):
        """Verify REST API dispatcher works completely offline."""
        router = PublicAPIV1Router()
        ctx = RequestContext(
            principal_id="usr_tester",
            organization_id="org_test",
            project_id="proj_test",
            role=EnterpriseRole.ORG_ADMIN,
        )
        status, res = router.handle_request("GET", "/api/v1/entitlements", ctx)
        self.assertEqual(status, 200)
        self.assertIn("entitlements", res)

        status, job_res = router.handle_request("POST", "/api/v1/jobs", ctx, payload={"task": "Offline Task"})
        self.assertEqual(status, 201)
        self.assertEqual(job_res["status"], "CREATED")

    def test_08_autonomous_engineering_loop_init(self):
        """Verify AutonomousEngineeringLoop defaults to local Ollama zero-cost provider."""
        loop = AutonomousEngineeringLoop()
        self.assertIsInstance(loop.provider, OllamaAdapter)
        task = loop.create_task("task_001", "proj_001", "Refactor error handling")
        self.assertEqual(task.task_id, "task_001")
        self.assertEqual(task.status.value, "CREATED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
