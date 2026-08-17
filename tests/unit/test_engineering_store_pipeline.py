from types import SimpleNamespace

import zcoder.services.engineering_store_pipeline as composition


def test_store_pipeline_composition_forwards_bounded_inputs(monkeypatch):
    calls = SimpleNamespace(executor=[], ledger=[], pipeline=[])
    executor = object()
    ledger = object()
    pipeline = object()
    store = object()
    run_lease = object()
    close_callback = object()

    def fake_executor(repository_root, **kwargs):
        calls.executor.append((repository_root, kwargs))
        return executor

    def fake_ledger(actual_store, *, namespace):
        calls.ledger.append((actual_store, namespace))
        return ledger

    def fake_pipeline(actual_executor, actual_ledger, **kwargs):
        calls.pipeline.append((actual_executor, actual_ledger, kwargs))
        return pipeline

    def work_source():
        return ()

    monkeypatch.setattr(composition, "_build_upgrade20_executor", fake_executor)
    monkeypatch.setattr(composition, "EngineeringStoreUpgradeLedger", fake_ledger)
    monkeypatch.setattr(composition, "ContinuousEngineeringPipeline", fake_pipeline)

    policy = object()
    github = object()
    result = composition.build_engineering_store_pipeline(
        "/repo",
        store,
        ledger_namespace="upgrade-test",
        run_lease=run_lease,
        project_id="project-test",
        allow_push=True,
        policy=policy,
        retry_blocked=True,
        work_sources=(work_source,),
        github_orchestrator=github,
        max_ci_repairs=2,
        close_callback=close_callback,
    )

    assert result is pipeline
    assert calls.executor == [
        (
            "/repo",
            {
                "project_id": "project-test",
                "allow_push": True,
                "github_orchestrator": github,
                "max_ci_repairs": 2,
            },
        )
    ]
    assert calls.ledger == [(store, "upgrade-test")]
    assert calls.pipeline == [
        (
            executor,
            ledger,
            {
                "work_sources": (work_source,),
                "policy": policy,
                "retry_blocked": True,
                "run_lease": run_lease,
                "close_callback": close_callback,
            },
        )
    ]
