from types import SimpleNamespace

from zcoder.interfaces.cli import continuous_engineering as composition


def test_run_sqlite_store_pipeline_once_runs_and_closes_exactly_once(monkeypatch):
    calls = []
    report = SimpleNamespace(state="completed")

    class FakePipeline:
        def run(self, seed_items):
            calls.append(("run", tuple(seed_items)))
            return report

        def close(self):
            calls.append(("close",))

    def fake_build(repository_root, db_path, **kwargs):
        calls.append(("build", repository_root, db_path, kwargs))
        return FakePipeline()

    monkeypatch.setattr(composition, "build_sqlite_store_pipeline", fake_build)
    seeds = (SimpleNamespace(item_id="one"),)

    result = composition.run_sqlite_store_pipeline_once(
        "/repo",
        "/state/engineering.db",
        seeds,
        ledger_namespace="tenant-a",
        max_ci_repairs=2,
    )

    assert result is report
    assert calls == [
        (
            "build",
            "/repo",
            "/state/engineering.db",
            {"ledger_namespace": "tenant-a", "max_ci_repairs": 2},
        ),
        ("run", seeds),
        ("close",),
    ]


def test_run_sqlite_store_pipeline_once_closes_after_failure(monkeypatch):
    calls = []

    class FakePipeline:
        def run(self, seed_items):
            calls.append(("run", tuple(seed_items)))
            raise RuntimeError("boom")

        def close(self):
            calls.append(("close",))

    monkeypatch.setattr(
        composition,
        "build_sqlite_store_pipeline",
        lambda repository_root, db_path, **kwargs: FakePipeline(),
    )

    try:
        composition.run_sqlite_store_pipeline_once("/repo", "/state/engineering.db")
    except RuntimeError as exc:
        assert str(exc) == "boom"
    else:
        raise AssertionError("expected bounded run failure")

    assert calls == [("run", ()), ("close",)]
