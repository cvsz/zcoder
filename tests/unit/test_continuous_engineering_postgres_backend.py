"""Unit coverage for Upgrade-33 PostgreSQL backend exposure and lifecycle."""

from types import SimpleNamespace

import pytest

import zcoder.services.continuous_engineering as continuous_engineering
from zcoder.services.upgrade_loop import LoopReport, LoopState


class FakePipeline:
    def __init__(self):
        self.ledger = SimpleNamespace(terminal_counts=lambda: {"SUCCEEDED": 0, "BLOCKED": 0})
        self.closed = False

    def close(self):
        self.closed = True

    def run(self, seed):
        return LoopReport(
            state=LoopState.COMPLETED,
            iterations=0,
            completed_item_ids=(),
            blocked_item_ids=(),
            pending_item_ids=(),
            records=(),
        )


def test_cli_exposes_postgres_without_changing_json_default():
    defaults = continuous_engineering.build_parser().parse_args([])
    postgres = continuous_engineering.build_parser().parse_args(["--state-backend", "postgres"])

    assert defaults.state_backend == "json"
    assert postgres.state_backend == "postgres"


def test_postgres_cli_requires_database_url(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ValueError, match="DATABASE_URL must be set"):
        continuous_engineering.main(["--repository", str(tmp_path), "--state-backend", "postgres"])


def test_postgres_cli_routes_environment_secret_without_printing_it(tmp_path, monkeypatch, capsys):
    secret = "postgresql://secret-user:secret-password@db.example.invalid/zcoder"
    captured = {}
    pipeline = FakePipeline()
    monkeypatch.setenv("DATABASE_URL", secret)

    def fake_builder(repository_root, database_url, **kwargs):
        captured["repository_root"] = repository_root
        captured["database_url"] = database_url
        captured.update(kwargs)
        return pipeline

    monkeypatch.setattr(continuous_engineering, "build_postgres_store_pipeline", fake_builder)

    result = continuous_engineering.main(
        [
            "--repository",
            str(tmp_path),
            "--state-backend",
            "postgres",
            "--ledger-namespace",
            "fleet-prod",
        ]
    )

    output = capsys.readouterr().out
    assert result == 0
    assert captured["repository_root"] == tmp_path.resolve()
    assert captured["database_url"] == secret
    assert captured["ledger_namespace"] == "fleet-prod"
    assert pipeline.closed is True
    assert secret not in output
    assert "secret-password" not in output


def test_pipeline_close_is_idempotent_and_run_after_close_fails(tmp_path):
    closed = []
    executor = SimpleNamespace()
    ledger = SimpleNamespace(path=tmp_path / "state.json")
    pipeline = continuous_engineering.ContinuousEngineeringPipeline(
        executor,
        ledger,
        close_callback=lambda: closed.append(True),
    )

    pipeline.close()
    pipeline.close()

    assert closed == [True]
    with pytest.raises(RuntimeError, match="pipeline is closed"):
        pipeline.run([])


def test_postgres_builder_rejects_empty_database_url_before_store_construction():
    with pytest.raises(ValueError, match="database_url must not be empty"):
        continuous_engineering.build_postgres_store_pipeline(".", "")
