"""Performance benchmarks for zcoder core operations."""

from __future__ import annotations

import statistics
import time
from pathlib import Path
from typing import Any


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = max(0, int(percentile * len(ordered)) - 1)
    return ordered[index]


def _bench(name: str, fn, *, warmups: int = 3, repeats: int = 100) -> dict[str, Any]:
    """Run a benchmark with warmups and repeats, return timing stats."""
    for _ in range(warmups):
        fn()
    samples: list[float] = []
    for _ in range(repeats):
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1000.0)  # ms
    avg = statistics.mean(samples)
    p50 = _percentile(samples, 0.50)
    p95 = _percentile(samples, 0.95)
    p99 = _percentile(samples, 0.99)
    print(f"  {name}: avg={avg:.3f}ms p50={p50:.3f}ms p95={p95:.3f}ms p99={p99:.3f}ms (n={repeats})")
    return {"name": name, "avg_ms": avg, "p50_ms": p50, "p95_ms": p95, "p99_ms": p99, "n": repeats}


def run_session_benchmarks(*, warmups: int = 3, repeats: int = 100) -> list[dict[str, Any]]:
    """Benchmarks for session store and projection operations."""
    from zcoder.agent.codeagent.sessions import (
        SessionEvent,
        SessionProjection,
        SessionStore,
    )

    results: list[dict[str, Any]] = []

    print("=" * 60)
    print("zcoder session benchmarks")
    print("=" * 60)

    # Setup: temporary store
    import tempfile

    tmpdir = Path(tempfile.mkdtemp(prefix="zcoder-bench-sessions-"))
    store = SessionStore(directory=tmpdir)

    messages = [
        {"role": "user", "content": "Hello, how are you?"},
        {"role": "assistant", "content": "I'm fine, thank you!"},
        {"role": "user", "content": "What is 2+2?"},
        {"role": "assistant", "content": "2+2 equals 4."},
    ]

    def save_session():
        store.save("20260115-120000-000001", str(tmpdir), messages)

    def load_session():
        store.load("20260115-120000-000001")

    results.append(_bench("SessionStore.save", save_session, warmups=warmups, repeats=repeats))
    results.append(_bench("SessionStore.load", load_session, warmups=warmups, repeats=repeats))

    # List sessions
    results.append(
        _bench("SessionStore.list_sessions", store.list_sessions, warmups=warmups, repeats=repeats)
    )

    # Session projection fold_many
    events = [
        SessionEvent(
            kind="turn/start",
            data={"turn": 1},
            event_id=f"evt-{i}",
            timestamp=float(i),
        )
        for i in range(50)
    ]

    def fold_many():
        p = SessionProjection()
        p.fold_many(events)

    results.append(
        _bench("SessionProjection.fold_many(50 events)", fold_many, warmups=warmups, repeats=repeats)
    )

    # SessionEvent serialization round-trip
    event = SessionEvent(
        kind="user/message",
        data={"content": "Hello world", "turn": 1},
        event_id="evt-1",
        timestamp=1000.0,
    )

    def serialize_roundtrip():
        from zcoder.agent.codeagent.sessions import session_event_to_dict

        d = session_event_to_dict(event)
        SessionEvent(
            kind=d["kind"],
            data=d.get("data", {}),
            source_event_seqs=d.get("source_event_seqs"),
            ignorable=d.get("ignorable", False),
            surface_op=d.get("surface_op", d.get("surfaceOp")),
            event_id=str(d.get("event_id", d.get("eventId", ""))),
            timestamp=float(d.get("timestamp", 0.0)),
        )

    results.append(
        _bench("SessionEvent serialize round-trip", serialize_roundtrip, warmups=warmups, repeats=repeats)
    )

    print()
    return results


def run_llm_benchmarks(*, warmups: int = 3, repeats: int = 1000) -> list[dict[str, Any]]:
    """Benchmarks for LLM token estimation and context reporting."""
    from zcoder.agent.capabilities.code import estimate_tokens, render_context_report

    results: list[dict[str, Any]] = []

    print("=" * 60)
    print("zcoder LLM/util benchmarks")
    print("=" * 60)

    short_text = "Hello world"
    medium_text = " ".join(["word"] * 100)
    long_text = " ".join(["sentence"] * 1000)

    results.append(
        _bench(
            "estimate_tokens(short)", lambda: estimate_tokens(short_text), warmups=warmups, repeats=repeats
        )
    )
    results.append(
        _bench(
            "estimate_tokens(medium)", lambda: estimate_tokens(medium_text), warmups=warmups, repeats=repeats
        )
    )
    results.append(
        _bench("estimate_tokens(long)", lambda: estimate_tokens(long_text), warmups=warmups, repeats=repeats)
    )

    rep = {"window": 32768, "used": 8192, "system": 1024, "tools": 512, "conversation": 2048}
    results.append(
        _bench(
            "render_context_report",
            lambda: render_context_report(rep, model="zcoder-pro"),
            warmups=warmups,
            repeats=repeats,
        )
    )

    print()
    return results


def run_plugin_benchmarks(*, warmups: int = 3, repeats: int = 100) -> list[dict[str, Any]]:
    """Benchmarks for plugin manager operations."""
    from unittest.mock import patch

    from zcoder.agent.plugin.loader import PluginLoader
    from zcoder.agent.plugin.manager import PluginManager, PluginTier
    from zcoder.agent.plugin.manifest import PluginManifest

    results: list[dict[str, Any]] = []

    print("=" * 60)
    print("zcoder plugin benchmarks")
    print("=" * 60)

    def make_plugins(count: int = 20):
        from zcoder.agent.plugin.loader import LoadedPlugin

        plugins = []
        for i in range(count):
            tier = list(PluginTier)[i % len(PluginTier)]
            plugins.append(
                LoadedPlugin(
                    manifest=PluginManifest(
                        name=f"plugin-{i}",
                        version="1.0.0",
                        description="bench",
                        tier=tier.name.lower(),
                    ),
                    hooks={"turn/end": []},
                    tools={},
                    commands={},
                    mcp_servers={},
                    module=None,
                )
            )
        return plugins

    plugins = make_plugins(20)

    def load_all():
        manager = PluginManager()
        with patch.object(PluginLoader, "load_all_plugins", return_value=plugins):
            manager.load_all()
        return manager

    def get_all_ordered(manager):
        return manager.get_all_plugins_ordered()

    def get_hooks(manager):
        return manager.get_hooks_for_event("turn/end")

    def get_stats(manager):
        return manager.get_stats()

    manager = load_all()

    results.append(_bench("PluginManager.load_all(20 plugins)", load_all, warmups=warmups, repeats=repeats))
    results.append(
        _bench(
            "PluginManager.get_all_plugins_ordered",
            lambda: get_all_ordered(manager),
            warmups=warmups,
            repeats=repeats,
        )
    )
    results.append(
        _bench(
            "PluginManager.get_hooks_for_event",
            lambda: get_hooks(manager),
            warmups=warmups,
            repeats=repeats,
        )
    )
    results.append(
        _bench(
            "PluginManager.get_stats",
            lambda: get_stats(manager),
            warmups=warmups,
            repeats=repeats,
        )
    )

    print()
    return results


def run_all_benchmarks(*, warmups: int = 3, repeats: int = 100) -> dict[str, list[dict[str, Any]]]:
    """Run all benchmark suites."""
    all_results: dict[str, list[dict[str, Any]]] = {}
    all_results["sessions"] = run_session_benchmarks(warmups=warmups, repeats=repeats)
    all_results["llm"] = run_llm_benchmarks(warmups=warmups, repeats=repeats * 10)
    all_results["plugins"] = run_plugin_benchmarks(warmups=warmups, repeats=repeats)
    return all_results


if __name__ == "__main__":
    run_all_benchmarks()
