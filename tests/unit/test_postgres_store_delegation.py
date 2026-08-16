from zcoder.infrastructure.stores import postgres as postgres_store


def test_control_plane_store_process_outbox_delegates_once(monkeypatch):
    calls = []

    def fake_delegate(store, handler, *, max_attempts, backoff_base):
        calls.append((store, handler, max_attempts, backoff_base))
        return 4

    monkeypatch.setattr(postgres_store, "process_postgres_store_outbox", fake_delegate)

    store = object.__new__(postgres_store.PostgresControlPlaneStore)
    handler = object()

    assert store.process_outbox(handler, max_attempts=3, backoff_base=7.0) == 4
    assert calls == [(store, handler, 3, 7.0)]
