from zcoder.infrastructure.stores import postgres_outbox_store


def test_store_adapter_preserves_legacy_defaults(monkeypatch):
    calls = []

    def fake_process(store, handler, *, max_messages, max_attempts):
        calls.append((store, handler, max_messages, max_attempts))
        return 3

    monkeypatch.setattr(postgres_outbox_store, "process_postgres_outbox_once", fake_process)
    store = object()
    handler = object()

    assert postgres_outbox_store.process_postgres_store_outbox(store, handler) == 3
    assert calls == [(store, handler, 50, 5)]


def test_store_adapter_forwards_explicit_finite_budgets(monkeypatch):
    calls = []

    def fake_process(store, handler, *, max_messages, max_attempts):
        calls.append((max_messages, max_attempts))
        return 0

    monkeypatch.setattr(postgres_outbox_store, "process_postgres_outbox_once", fake_process)

    assert (
        postgres_outbox_store.process_postgres_store_outbox(
            object(),
            object(),
            max_attempts=2,
            backoff_base=99.0,
            max_messages=7,
        )
        == 0
    )
    assert calls == [(7, 2)]


def test_store_adapter_does_not_retry_when_processor_fails(monkeypatch):
    calls = 0

    def fail_once(store, handler, *, max_messages, max_attempts):
        nonlocal calls
        calls += 1
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(postgres_outbox_store, "process_postgres_outbox_once", fail_once)

    try:
        postgres_outbox_store.process_postgres_store_outbox(object(), object())
    except RuntimeError as exc:
        assert str(exc) == "database unavailable"
    else:
        raise AssertionError("processor failure must surface")

    assert calls == 1
