from types import SimpleNamespace

import zcoder.interfaces.cli.continuous_engineering as cli
from zcoder.services.upgrade_loop import LoopReport, LoopState


def test_outward_cli_preserves_sqlite_routing_contract(tmp_path, monkeypatch, capsys):
    captured = {}
    fake_ledger = SimpleNamespace(terminal_counts=lambda: {"SUCCEEDED": 0, "BLOCKED": 0})
    fake_report = LoopReport(
        state=LoopState.COMPLETED,
        iterations=0,
        completed_item_ids=(),
        blocked_item_ids=(),
        pending_item_ids=(),
        records=(),
    )
    fake_pipeline = SimpleNamespace(
        ledger=fake_ledger,
        run=lambda seed: fake_report,
        close=lambda: captured.setdefault("closed", True),
    )

    def fake_builder(repository_root, db_path, **kwargs):
        captured["repository_root"] = repository_root
        captured["db_path"] = db_path
        captured.update(kwargs)
        return fake_pipeline

    monkeypatch.setattr(cli, "build_sqlite_store_pipeline", fake_builder)

    result = cli.main(
        [
            "--repository",
            str(tmp_path),
            "--state-backend",
            "sqlite",
            "--engineering-db",
            "state/engineering.db",
            "--ledger-namespace",
            "fleet-main",
        ]
    )

    assert result == 0
    assert captured["repository_root"] == tmp_path.resolve()
    assert captured["db_path"] == tmp_path.resolve() / "state/engineering.db"
    assert captured["ledger_namespace"] == "fleet-main"
    assert captured["closed"] is True
    assert '"state": "COMPLETED"' in capsys.readouterr().out


def test_outward_cli_parser_preserves_existing_backend_defaults():
    defaults = cli.build_parser().parse_args([])
    sqlite = cli.build_parser().parse_args(
        ["--state-backend", "sqlite", "--engineering-db", "fleet.db", "--ledger-namespace", "fleet-a"]
    )

    assert defaults.state_backend == "json"
    assert defaults.state_file == ".zcoder/upgrade-loop-state.json"
    assert sqlite.state_backend == "sqlite"
    assert sqlite.engineering_db == "fleet.db"
    assert sqlite.ledger_namespace == "fleet-a"
