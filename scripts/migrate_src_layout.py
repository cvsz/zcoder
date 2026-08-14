#!/usr/bin/env python3
"""Reproducible mapping for the zcoder flat-module -> src-layout migration.

Dry-run is the default. ``--apply`` moves only sources whose destination does
not already exist, making the script safe to re-run after a partial migration.
"""
import argparse
import shutil
from pathlib import Path

MAPPING = {
    "agent_runtime.py": "src/zcoder/services/agent_runtime.py",
    "anthropic_conformance.py": "src/zcoder/api/anthropic_conformance.py",
    "artifacts.py": "src/zcoder/infrastructure/artifacts.py",
    "auth_oidc.py": "src/zcoder/infrastructure/auth/oidc.py",
    "backup_restore.py": "src/zcoder/services/backup_restore.py",
    "claude_admin_api.py": "src/zcoder/claude/enterprise/admin_api.py",
    "claude_advisor.py": "src/zcoder/claude/capabilities/advisor.py",
    "claude_agents_sdk.py": "src/zcoder/claude/orchestration/agents_sdk.py",
    "claude_batch.py": "src/zcoder/claude/orchestration/batch.py",
    "claude_cache.py": "src/zcoder/claude/memory/cache.py",
    "claude_chrome.py": "src/zcoder/claude/integrations/chrome.py",
    "claude_citations.py": "src/zcoder/claude/capabilities/citations.py",
    "claude_code.py": "src/zcoder/claude/capabilities/code.py",
    "claude_code_exec.py": "src/zcoder/claude/capabilities/code_exec.py",
    "claude_compliance_api.py": "src/zcoder/claude/enterprise/compliance.py",
    "claude_cost_optimizer.py": "src/zcoder/claude/optimization/cost.py",
    "claude_embeddings.py": "src/zcoder/claude/capabilities/embeddings.py",
    "claude_eval.py": "src/zcoder/claude/eval/eval.py",
    "claude_evals.py": "src/zcoder/claude/eval/evals.py",
    "claude_excel.py": "src/zcoder/claude/integrations/excel.py",
    "claude_fable5.py": "src/zcoder/claude/models/fable5.py",
    "claude_files.py": "src/zcoder/claude/integrations/files.py",
    "claude_git.py": "src/zcoder/claude/integrations/git.py",
    "claude_github.py": "src/zcoder/claude/integrations/github.py",
    "claude_haiku45.py": "src/zcoder/claude/models/haiku45.py",
    "claude_hooks_perms_plan.py": "src/zcoder/claude/enterprise/hooks_perms.py",
    "claude_interactive.py": "src/zcoder/claude/orchestration/interactive.py",
    "claude_live.py": "src/zcoder/claude/orchestration/live.py",
    "claude_mcp_connector.py": "src/zcoder/claude/tools/mcp.py",
    "claude_memory.py": "src/zcoder/claude/memory/memory.py",
    "claude_metrics.py": "src/zcoder/claude/enterprise/metrics.py",
    "claude_model_preflight.py": "src/zcoder/claude/models/preflight.py",
    "claude_models.py": "src/zcoder/claude/models/registry.py",
    "claude_mythos5.py": "src/zcoder/claude/models/mythos5.py",
    "claude_observability.py": "src/zcoder/claude/observability.py",
    "claude_opus5.py": "src/zcoder/claude/models/opus5.py",
    "claude_output_styles.py": "src/zcoder/claude/eval/output_styles.py",
    "claude_plugins.py": "src/zcoder/claude/tools/plugins.py",
    "claude_powerpoint.py": "src/zcoder/claude/integrations/powerpoint.py",
    "claude_prompt_optimizer.py": "src/zcoder/claude/optimization/prompt.py",
    "claude_rag.py": "src/zcoder/claude/rag/engine.py",
    "claude_research.py": "src/zcoder/claude/rag/research.py",
    "claude_router.py": "src/zcoder/claude/orchestration/router.py",
    "claude_sandbox.py": "src/zcoder/claude/tools/sandbox.py",
    "claude_search.py": "src/zcoder/claude/capabilities/search.py",
    "claude_sessions.py": "src/zcoder/claude/orchestration/sessions.py",
    "claude_settings.py": "src/zcoder/claude/enterprise/settings.py",
    "claude_skills_api.py": "src/zcoder/claude/enterprise/skills.py",
    "claude_sonnet5.py": "src/zcoder/claude/models/sonnet5.py",
    "claude_stream.py": "src/zcoder/claude/capabilities/stream.py",
    "claude_structured.py": "src/zcoder/claude/capabilities/structured.py",
    "claude_thinking.py": "src/zcoder/claude/capabilities/thinking.py",
    "claude_tokens.py": "src/zcoder/claude/optimization/tokens.py",
    "claude_tools.py": "src/zcoder/claude/tools/registry.py",
    "claude_vision.py": "src/zcoder/claude/capabilities/vision.py",
    "claude_wif.py": "src/zcoder/claude/integrations/wif.py",
    "claude_workflow.py": "src/zcoder/claude/orchestration/workflow.py",
    "coder.py": "src/zcoder/services/coder.py",
    "compliance_evidence.py": "src/zcoder/services/compliance_evidence.py",
    "config.py": "src/zcoder/config/settings.py",
    "control_plane.py": "src/zcoder/domain/services/control_plane.py",
    "cowork.py": "src/zcoder/services/cowork.py",
    "deployment_engine.py": "src/zcoder/domain/services/deployment.py",
    "engineering_models.py": "src/zcoder/domain/models/engineering.py",
    "engineering_orchestrator.py": "src/zcoder/services/engineering_orchestrator.py",
    "engineering_store_interface.py": "src/zcoder/domain/interfaces/engineering_store.py",
    "engineering_worker.py": "src/zcoder/services/engineering_worker.py",
    "enterprise_postgres_store.py": "src/zcoder/infrastructure/stores/enterprise_postgres.py",
    "exceptions.py": "src/zcoder/core/exceptions.py",
    "github_orchestrator.py": "src/zcoder/services/github_orchestrator.py",
    "health.py": "src/zcoder/core/health.py",
    "intelligence_models.py": "src/zcoder/domain/models/intelligence.py",
    "legacy_job_models.py": "src/zcoder/domain/models/legacy_job.py",
    "local_ai_stack.py": "src/zcoder/enterprise/local_ai_stack.py",
    "logging_config.py": "src/zcoder/config/logging.py",
    "maintenance_intelligence_service.py": "src/zcoder/services/maintenance_intelligence.py",
    "no_cost_platform.py": "src/zcoder/enterprise/no_cost_platform.py",
    "observability_otel.py": "src/zcoder/infrastructure/observability/otel.py",
    "personalities.py": "src/zcoder/claude/personalities.py",
    "policy_engine.py": "src/zcoder/domain/services/policy_engine.py",
    "portfolio_models.py": "src/zcoder/domain/models/portfolio.py",
    "portfolio_scheduler.py": "src/zcoder/services/portfolio_scheduler.py",
    "portfolio_store.py": "src/zcoder/infrastructure/stores/portfolio.py",
    "postgres_engineering_store.py": "src/zcoder/infrastructure/stores/postgres_engineering.py",
    "postgres_store.py": "src/zcoder/infrastructure/stores/postgres.py",
    "product_models.py": "src/zcoder/domain/models/product.py",
    "production_config.py": "src/zcoder/config/production.py",
    "projects.py": "src/zcoder/services/projects.py",
    "public_api_v1.py": "src/zcoder/api/public/v1.py",
    "release_gate.py": "src/zcoder/services/release_gate.py",
    "residency_models.py": "src/zcoder/domain/models/residency.py",
    "resilience.py": "src/zcoder/core/resilience.py",
    "scim_service.py": "src/zcoder/infrastructure/auth/scim.py",
    "sdk_client.py": "src/zcoder/interfaces/sdk/client.py",
    "security.py": "src/zcoder/core/security.py",
    "skills.py": "src/zcoder/services/skills.py",
    "sqlite_engineering_store.py": "src/zcoder/infrastructure/stores/sqlite_engineering.py",
    "tenant_models.py": "src/zcoder/domain/models/tenant.py",
    "tui.py": "src/zcoder/interfaces/cli/tui.py",
    "tui_streaming.py": "src/zcoder/interfaces/cli/streaming.py",
    "utils.py": "src/zcoder/core/utils.py",
    "worker_process.py": "src/zcoder/worker/process.py",
}


def migrate(root, apply_changes=False):
    """Return migration actions and optionally apply safe file moves."""
    actions = []
    for source_name, destination_name in MAPPING.items():
        source = root / source_name
        destination = root / destination_name
        if destination.exists():
            state = "already-migrated"
        elif not source.exists():
            state = "missing-source"
        elif apply_changes:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(destination))
            state = "moved"
        else:
            state = "would-move"
        actions.append((source_name, destination_name, state))
    return actions


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="apply safe moves")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()

    actions = migrate(args.root.resolve(), args.apply)
    for source, destination, state in actions:
        print(f"{state:16} {source} -> {destination}")

    unresolved = [item for item in actions if item[2] == "missing-source"]
    return 1 if unresolved else 0


if __name__ == "__main__":
    raise SystemExit(main())
