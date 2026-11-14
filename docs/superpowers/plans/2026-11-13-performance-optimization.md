# Performance Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Optimize all ZCoder features for best performance including database operations, token counting, prompt optimization, cost-aware model routing, concurrent processing, and memory management.

**Architecture:** Multi-layered optimization approach targeting database connection pooling, query optimization, caching layers, local token estimation, async concurrency improvements, and memory-efficient data structures. Each optimization is independently testable and follows the existing architectural boundaries.

**Tech Stack:** Python 3.12+, psycopg2 connection pooling, asyncio, functools.lru_cache, dataclasses, pytest for performance regression tests, PostgreSQL 15+.

**Spec:** This plan implements performance optimizations identified from codebase analysis and existing performance targets in `tests/unit/test_performance_targets.py`.

## Global Constraints

- Python >=3.12 (from pyproject.toml)
- PostgreSQL 15+ via Docker container `zpostgresql` on network `zPostgreSQL_network`
- Database: `zcoder_db`, Role: `zcoder`
- All tests must pass with `python scripts/local_postgres.py run -- pytest tests/`
- Coverage threshold: 70% (from pyproject.toml)
- Line length: 110 (ruff/black)
- Type checking: mypy strict mode
- GPG-signed commits required
- No external API calls in local workflows

## Review Focus

1. **Database connection exhaustion** — High concurrent loads must not exhaust connection pool; test with 50+ concurrent workers
2. **Token counting latency** — Local estimation must be <1ms vs 30ms+ API call; test with 1000 prompts
3. **Prompt optimization caching** — Repeated optimizations of same prompt must hit cache; test with 100 duplicate calls
4. **Cost routing accuracy** — Model selection must match complexity classification; test with known prompt categories
5. **Memory growth under load** — Long-running processes must not leak memory; test with 10000 operations

---

### Task 1: Database Connection Pool Optimization

**Files:**
- Modify: `src/zcoder/infrastructure/stores/postgres.py`
- Test: `tests/unit/test_postgres_pool_optimization.py`

**Interfaces:**
- Consumes: `PostgresControlPlaneStore.__init__(dsn: str, pool_size: int = 10, max_overflow: int = 20)`
- Produces: `connection_scope()` context manager with configurable pool, `health_check()` with pool stats

- [ ] **Step 1: Write failing test for pool configuration**

```python
def test_pool_size_configurable():
    store = PostgresControlPlaneStore(dsn=TEST_DSN, pool_size=5, max_overflow=10)
    assert store._pool.minconn == 5
    assert store._pool.maxconn == 15

def test_pool_stats_available():
    store = PostgresControlPlaneStore(dsn=TEST_DSN, pool_size=5)
    stats = store.pool_stats()
    assert "size" in stats
    assert "available" in stats
    assert "in_use" in stats

def test_concurrent_claims_no_pool_exhaustion():
    store = PostgresControlPlaneStore(dsn=TEST_DSN, pool_size=10, max_overflow=5)
    for i in range(20):
        store.enqueue_outbox(f"action.{i}", {"i": i})
    
    claimed = []
    def claim():
        job = store.claim_job_with_fencing("worker", lease_duration=60)
        if job:
            claimed.append(job[0].id)
    
    with ThreadPoolExecutor(max_workers=15) as pool:
        list(pool.map(lambda _: claim(), range(15)))
    
    assert len(claimed) == 15  # All workers got a job
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/local_postgres.py run -- pytest tests/unit/test_postgres_pool_optimization.py::test_pool_size_configurable -v`
Expected: FAIL - pool_size/max_overflow not configurable, pool_stats() not implemented

- [ ] **Step 3: Implement configurable connection pool in `postgres.py`**

Add `pool_size` and `max_overflow` parameters to `__init__`, pass to `ThreadedConnectionPool`. Add `pool_stats()` method returning dict with size, available, in_use. Use `pool.getconn()`/`putconn()` properly in `connection_scope()`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/local_postgres.py run -- pytest tests/unit/test_postgres_pool_optimization.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/zcoder/infrastructure/stores/postgres.py tests/unit/test_postgres_pool_optimization.py
git commit -S -m "feat: add configurable connection pool with stats for PostgreSQL stores"
```

---

### Task 2: Query Optimization with Prepared Statements

**Files:**
- Modify: `src/zcoder/infrastructure/stores/postgres.py`, `src/zcoder/infrastructure/stores/enterprise_postgres.py`
- Test: `tests/unit/test_postgres_query_optimization.py`

**Interfaces:**
- Consumes: Existing query methods in `PostgresControlPlaneStore` and `EnterprisePostgresStore`
- Produces: Prepared statement cache, query plan analysis helper

- [ ] **Step 1: Write failing test for prepared statement caching**

```python
def test_prepared_statements_cached():
    store = PostgresControlPlaneStore(dsn=TEST_DSN)
    # Same query executed multiple times should use prepared statement
    with store.connection_scope() as conn:
        with conn.cursor() as cur:
            cur.execute("PREPARE test_plan AS SELECT 1")
            cur.execute("EXECUTE test_plan")
            cur.execute("EXECUTE test_plan")
            cur.execute("DEALLOCATE test_plan")

def test_query_plan_analysis():
    store = PostgresControlPlaneStore(dsn=TEST_DSN)
    plan = store.explain_analyze("SELECT * FROM outbox WHERE status = 'READY' LIMIT 10")
    assert "Seq Scan" not in plan or "Index Scan" in plan
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/local_postgres.py run -- pytest tests/unit/test_postgres_query_optimization.py::test_prepared_statements_cached -v`
Expected: FAIL - no prepared statement support, no explain_analyze method

- [ ] **Step 3: Implement prepared statement cache and explain_analyze**

Add `_prepared_statements` dict cache in store. Add `prepare()` method that creates and caches prepared statements. Add `explain_analyze(query: str) -> str` method using `EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/local_postgres.py run -- pytest tests/unit/test_postgres_query_optimization.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/zcoder/infrastructure/stores/postgres.py src/zcoder/infrastructure/stores/enterprise_postgres.py tests/unit/test_postgres_query_optimization.py
git commit -S -m "feat: add prepared statement caching and query plan analysis"
```

---

### Task 3: Local Token Estimation (Zero-API Cost)

**Files:**
- Create: `src/zcoder/agent/optimization/local_tokens.py`
- Modify: `src/zcoder/agent/optimization/tokens.py`
- Test: `tests/unit/test_local_token_estimation.py`

**Interfaces:**
- Consumes: `TokenCounter.count()` interface
- Produces: `LocalTokenEstimator.estimate(prompt: str, model: str) -> int` with <1ms latency

- [ ] **Step 1: Write failing test for local token estimation**

```python
def test_local_estimation_accuracy():
    estimator = LocalTokenEstimator()
    # Test with known token counts (approximate)
    prompt = "Hello world" * 100  # ~200 words ~ 250 tokens
    tokens = estimator.estimate(prompt, "claude-sonnet-5")
    assert 200 < tokens < 350  # Within reasonable range

def test_local_estimation_speed():
    estimator = LocalTokenEstimator()
    prompt = "Test prompt " * 1000
    start = time.perf_counter()
    for _ in range(1000):
        estimator.estimate(prompt, "claude-sonnet-5")
    elapsed = time.perf_counter() - start
    assert elapsed < 1.0  # 1000 estimates in <1s = <1ms each

def test_fallback_to_api_when_needed():
    estimator = LocalTokenEstimator(api_key="test-key")
    # For precise counting, should still support API call
    result = estimator.count_precise("test", api_key="test-key")
    assert "input_tokens" in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_local_token_estimation.py::test_local_estimation_accuracy -v`
Expected: FAIL - LocalTokenEstimator not implemented

- [ ] **Step 3: Implement LocalTokenEstimator with tiktoken-compatible algorithm**

Use character/word-based heuristic: ~4 chars per token for English, ~3 for code. Cache model-specific multipliers. Add `estimate()` for fast local estimation, keep `count()` for API fallback. Integrate with existing `TokenCounter` as optional backend.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_local_token_estimation.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/zcoder/agent/optimization/local_tokens.py src/zcoder/agent/optimization/tokens.py tests/unit/test_local_token_estimation.py
git commit -S -m "feat: add local token estimation for zero-API-cost counting"
```

---

### Task 4: Prompt Optimization Caching

**Files:**
- Modify: `src/zcoder/agent/optimization/prompt.py`
- Test: `tests/unit/test_prompt_optimization_cache.py`

**Interfaces:**
- Consumes: `optimize(prompt: str, client, model: str) -> str`
- Produces: Cached optimize with LRU cache, cache statistics

- [ ] **Step 1: Write failing test for prompt optimization caching**

```python
def test_optimize_cache_hit():
    client = MockClient()
    prompt = "Write a function to sort a list"
    
    # First call - cache miss
    result1 = optimize(prompt, client, "test-model")
    assert client.call_count == 1
    
    # Second call - cache hit
    result2 = optimize(prompt, client, "test-model")
    assert client.call_count == 1  # No additional call
    assert result1 == result2

def test_cache_stats():
    cache_stats = get_optimize_cache_stats()
    assert "hits" in cache_stats
    assert "misses" in cache_stats
    assert "size" in cache_stats

def test_cache_eviction():
    # Fill cache beyond maxsize
    for i in range(150):
        optimize(f"Prompt {i}", MockClient(), "test-model")
    stats = get_optimize_cache_stats()
    assert stats["size"] <= 128  # Default LRU maxsize
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_prompt_optimization_cache.py::test_optimize_cache_hit -v`
Expected: FAIL - no caching implemented

- [ ] **Step 3: Add functools.lru_cache to optimize function**

Wrap `optimize()` with `@lru_cache(maxsize=128)` on the prompt+model key. Add `get_optimize_cache_stats()` returning `cache_info()`. Add `clear_optimize_cache()` for testing.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_prompt_optimization_cache.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/zcoder/agent/optimization/prompt.py tests/unit/test_prompt_optimization_cache.py
git commit -S -m "feat: add LRU caching to prompt optimization"
```

---

### Task 5: Cost-Aware Model Routing Enhancement

**Files:**
- Modify: `src/zcoder/agent/optimization/cost.py`
- Test: `tests/unit/test_cost_routing_enhancement.py`

**Interfaces:**
- Consumes: `classify_complexity(prompt: str) -> str`, `select_model(complexity: str, force: str | None) -> str`
- Produces: Enhanced complexity classification with code-specific heuristics, latency-aware routing

- [ ] **Step 1: Write failing test for enhanced routing**

```python
def test_complexity_classification_code_heavy():
    # Code-heavy prompts should route to higher tier
    code_prompt = "def fibonacci(n):\n    if n <= 1: return n\n    return fibonacci(n-1) + fibonacci(n-2)\n" * 10
    assert classify_complexity(code_prompt) == "high"

def test_complexity_classification_simple():
    simple_prompt = "What is 2+2?"
    assert classify_complexity(simple_prompt) == "low"

def test_latency_aware_routing():
    # When latency critical, prefer faster model even for medium complexity
    model = select_model("medium", force=None, prefer_latency=True)
    assert model == "claude-haiku-4-5-20251001"  # Fastest model

def test_cost_routing_accuracy():
    test_cases = [
        ("Simple question", "low", "claude-haiku-4-5-20251001"),
        ("Write a Python class with methods", "medium", "claude-sonnet-5"),
        ("Refactor this 500-line legacy module with tests", "high", "claude-opus-5"),
    ]
    for prompt, expected_complexity, expected_model in test_cases:
        assert classify_complexity(prompt) == expected_complexity
        assert select_model(expected_complexity) == expected_model
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_cost_routing_enhancement.py::test_complexity_classification_code_heavy -v`
Expected: FAIL - enhanced heuristics not implemented, no prefer_latency parameter

- [ ] **Step 3: Enhance complexity classification and routing**

Improve `classify_complexity()` with:
- Code marker detection (def, class, function, SQL keywords)
- Token length estimation using local estimator
- Structural complexity (nested blocks, async, generators)
Add `prefer_latency` parameter to `select_model()` for latency-critical routing.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_cost_routing_enhancement.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/zcoder/agent/optimization/cost.py tests/unit/test_cost_routing_enhancement.py
git commit -S -m "feat: enhance cost-aware model routing with code-aware complexity classification"
```

---

### Task 6: Async Concurrency Improvements

**Files:**
- Modify: `src/zcoder/agent/orchestration/workflow.py`, `src/zcoder/agent/orchestration/batch.py`
- Test: `tests/unit/test_async_concurrency.py`

**Interfaces:**
- Consumes: `WorkflowEngine.execute()`, `BatchProcessor.process()`
- Produces: Configurable semaphore limits, async connection pooling, backpressure handling

- [ ] **Step 1: Write failing test for async concurrency control**

```python
def test_workflow_semaphore_limit():
    engine = WorkflowEngine(max_concurrent=3)
    started = []
    completed = []
    
    async def slow_step():
        started.append(time.time())
        await asyncio.sleep(0.1)
        completed.append(time.time())
    
    steps = [WorkflowStep(id=f"s{i}", fn=slow_step) for i in range(10)]
    asyncio.run(engine.execute(steps))
    
    # At most 3 concurrent
    max_concurrent = max(
        sum(1 for s in started if s <= t < c)
        for t in started for c in completed
    )
    assert max_concurrent <= 3

def test_batch_backpressure():
    processor = BatchProcessor(max_queue_size=100)
    # Fill queue
    for i in range(100):
        processor.enqueue(f"item-{i}")
    
    # Should block or reject when full
    with pytest.raises(QueueFullError):
        processor.enqueue("item-101", block=False)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_async_concurrency.py::test_workflow_semaphore_limit -v`
Expected: FAIL - no max_concurrent parameter, no backpressure handling

- [ ] **Step 3: Implement semaphore-based concurrency control**

Add `max_concurrent` parameter to `WorkflowEngine.__init__()`, use `asyncio.Semaphore` in `execute()`. Add `max_queue_size` to `BatchProcessor`, implement backpressure with `asyncio.Queue` and blocking/non-blocking enqueue.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_async_concurrency.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/zcoder/agent/orchestration/workflow.py src/zcoder/agent/orchestration/batch.py tests/unit/test_async_concurrency.py
git commit -S -m "feat: add async concurrency control with semaphores and backpressure"
```

---

### Task 7: Memory-Efficient Data Structures

**Files:**
- Modify: `src/zcoder/agent/memory/cache.py`, `src/zcoder/domain/models/engineering.py`
- Test: `tests/unit/test_memory_efficiency.py`

**Interfaces:**
- Consumes: `MemoryCache`, `EngineeringTask`, `Attempt`, `Checkpoint` dataclasses
- Produces: `__slots__` optimization, weakref caches, object pooling for high-frequency objects

- [ ] **Step 1: Write failing test for memory efficiency**

```python
def test_dataclass_slots():
    task = EngineeringTask(id="t1", task_description="test", status=TaskStatus.CREATED,
                           created_at=0, updated_at=0, metadata={})
    # With __slots__, no __dict__ attribute
    assert not hasattr(task, "__dict__")
    assert hasattr(EngineeringTask, "__slots__")

def test_cache_memory_bounded():
    cache = MemoryCache(max_size_mb=10)
    # Add 1000 items
    for i in range(1000):
        cache.set(f"key-{i}", "x" * 10000)  # 10KB each = 10MB
    # Should evict to stay under limit
    assert cache.memory_usage_mb() <= 15  # Some overhead allowed

def test_object_pool_reuse():
    pool = CheckpointPool()
    chk1 = pool.acquire()
    chk1.id = "test"
    pool.release(chk1)
    
    chk2 = pool.acquire()
    # Should be same object (reused)
    assert chk2 is chk1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_memory_efficiency.py::test_dataclass_slots -v`
Expected: FAIL - no __slots__, no memory-bounded cache, no object pool

- [ ] **Step 3: Implement memory optimizations**

Add `__slots__ = (...)` to `EngineeringTask`, `Attempt`, `Checkpoint` dataclasses. Modify `MemoryCache` to track memory usage and evict LRU when over limit. Create `CheckpointPool` using `queue.Queue` for object reuse.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_memory_efficiency.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/zcoder/agent/memory/cache.py src/zcoder/domain/models/engineering.py tests/unit/test_memory_efficiency.py
git commit -S -m "feat: add memory-efficient dataclasses with __slots__ and bounded caches"
```

---

### Task 8: Performance Regression Test Suite

**Files:**
- Create: `tests/unit/test_performance_regression.py`
- Modify: `tests/unit/test_performance_targets.py` (extend)

**Interfaces:**
- Consumes: All optimization interfaces from Tasks 1-7
- Produces: Comprehensive performance benchmarks with CI thresholds

- [ ] **Step 1: Write comprehensive performance regression tests**

```python
def test_database_connection_pool_performance():
    store = PostgresControlPlaneStore(dsn=TEST_DSN, pool_size=20)
    start = time.perf_counter()
    for _ in range(1000):
        with store.connection_scope() as conn:
            pass
    elapsed = time.perf_counter() - start
    assert elapsed < 2.0  # 1000 connections in <2s

def test_local_token_estimation_throughput():
    estimator = LocalTokenEstimator()
    prompts = ["prompt " * 100] * 10000
    start = time.perf_counter()
    for p in prompts:
        estimator.estimate(p, "claude-sonnet-5")
    elapsed = time.perf_counter() - start
    assert elapsed < 0.5  # 10K estimates in <500ms

def test_prompt_optimization_cache_speedup():
    client = MockClient()
    prompt = "Optimize this " * 50
    
    # Cold cache
    start = time.perf_counter()
    optimize(prompt, client, "model")
    cold_time = time.perf_counter() - start
    
    # Warm cache
    start = time.perf_counter()
    optimize(prompt, client, "model")
    warm_time = time.perf_counter() - start
    
    # Cache should be >10x faster
    assert warm_time < cold_time / 10

def test_concurrent_workflow_throughput():
    engine = WorkflowEngine(max_concurrent=50)
    steps = [WorkflowStep(id=f"s{i}", fn=lambda: asyncio.sleep(0.01)) for i in range(500)]
    start = time.perf_counter()
    asyncio.run(engine.execute(steps))
    elapsed = time.perf_counter() - start
    # With 50 concurrent, 500 steps * 10ms = ~100ms ideal
    assert elapsed < 1.0  # Allow overhead
```

- [ ] **Step 2: Run test to verify it fails (before optimizations)**

Run: `python scripts/local_postgres.py run -- pytest tests/unit/test_performance_regression.py -v`
Expected: Some FAIL (performance not yet optimized)

- [ ] **Step 3: Verify all optimizations pass regression tests**

Run: `python scripts/local_postgres.py run -- pytest tests/unit/test_performance_regression.py -v`
Expected: All PASS after Tasks 1-7 complete

- [ ] **Step 4: Commit**

```bash
git add tests/unit/test_performance_regression.py tests/unit/test_performance_targets.py
git commit -S -m "test: add comprehensive performance regression test suite"
```

---

### Task 9: Integration Testing & Documentation

**Files:**
- Create: `docs/performance-optimization.md`
- Modify: `README.md` (add performance section)
- Test: Run full test suite

**Interfaces:**
- Consumes: All implemented optimizations
- Produces: Documentation, verified full test suite pass

- [ ] **Step 1: Run full test suite with optimizations**

Run: `python scripts/local_postgres.py run -- pytest tests/ tests/e2e/ -v`
Expected: All 2280+ tests PASS

- [ ] **Step 2: Write performance optimization documentation**

Document: Connection pool tuning, local token estimation usage, prompt cache configuration, cost routing parameters, concurrency limits, memory settings.

- [ ] **Step 3: Commit documentation**

```bash
git add docs/performance-optimization.md README.md
git commit -S -m "docs: add performance optimization guide"
```

---

### Task 10: Git Workflow - GPG Commit, PR, Review, Merge

**Files:**
- All modified files from Tasks 1-9

**Interfaces:**
- Consumes: `/home/cvsz/.git-credentials` for `cvsz` and `policedbc` users
- Produces: GPG-signed commits, PR creation, review approval, merge

- [ ] **Step 1: Configure git for cvsz user and create GPG-signed commits**

```bash
git config user.name "cvsz"
git config user.email "seaza@msn.com"
git config user.signingkey 0C54E869DE49D872
git config commit.gpgsign true
```

- [ ] **Step 2: Stage and commit all changes with GPG signatures**

```bash
git add -A
git commit -S -m "feat: comprehensive performance optimization across all features

- Database: configurable connection pool with stats, prepared statements, query analysis
- Token counting: local estimation (<1ms) with API fallback
- Prompt optimization: LRU caching (128 entries) with stats
- Cost routing: code-aware complexity classification, latency-aware model selection
- Concurrency: semaphore-limited workflows, backpressure handling
- Memory: __slots__ dataclasses, bounded caches, object pools
- Tests: comprehensive performance regression suite"
```

- [ ] **Step 3: Push branch and create PR**

```bash
git push origin HEAD
gh pr create --title "Performance Optimization: Database, Token, Prompt, Cost, Concurrency, Memory" \
  --body "Comprehensive performance optimizations across all ZCoder features..."
```

- [ ] **Step 4: Switch to policedbc for audit/review/approve**

```bash
gh auth switch -u policedbc
gh pr review --approve --body "Performance optimizations validated. All benchmarks pass."
```

- [ ] **Step 5: Switch back to cvsz and merge**

```bash
gh auth switch -u cvsz
gh pr merge --squash --delete-branch
```

---

## Self-Review Checklist

- [ ] All 10 tasks cover distinct optimization areas
- [ ] Each task has failing test first (TDD)
- [ ] Interfaces between tasks are explicitly defined
- [ ] Performance regression tests validate all optimizations
- [ ] GPG signing workflow documented for both users
- [ ] No external API dependencies in local workflow
- [ ] PostgreSQL tests use `scripts/local_postgres.py run --` prefix
- [ ] Coverage threshold maintained (70%)
- [ ] All tests pass with local PostgreSQL