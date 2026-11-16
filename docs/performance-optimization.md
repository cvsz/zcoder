# ZCoder Performance Optimization Guide

This document describes the performance optimizations implemented in ZCoder v1.60.0+.

## Overview

ZCoder includes several performance optimization layers:

1. **Database Connection Pooling** - Configurable PostgreSQL connection pools with statistics
2. **Local Token Estimation** - Zero-API-cost token counting with <1ms latency
3. **Prompt Optimization Caching** - LRU cache for repeated prompt optimizations
4. **Cost-Aware Model Routing** - Intelligent model selection based on prompt complexity
5. **Async Concurrency Control** - Semaphore-limited workflows with backpressure
6. **Memory-Efficient Data Structures** - `__slots__` dataclasses, bounded caches, object pools

## Database Connection Pooling

### Configuration

```python
from zcoder.infrastructure.stores.postgres import PostgresControlPlaneStore

store = PostgresControlPlaneStore(
    dsn="postgresql://user:pass@host/db",
    min_conn=5,      # Minimum connections (default: 1)
    max_conn=20,     # Maximum connections (default: 10)
    connect_timeout=10
)
```

### Pool Statistics

```python
stats = store.pool_stats()
# Returns: {"size": 20, "available": 18, "in_use": 2}
```

### Prepared Statements

```python
# Prepare a statement for repeated execution
store.prepare("get_ready_jobs", "SELECT * FROM jobs WHERE status = 'READY' LIMIT %s")

# Execute with parameters
rows = store.execute_prepared("get_ready_jobs", (10,))

# Query plan analysis
plan = store.explain_analyze("SELECT * FROM jobs WHERE status = 'READY' LIMIT 10")
```

### Tuning Guidelines

| Workload | min_conn | max_conn |
|----------|----------|----------|
| Light (few workers) | 2 | 5 |
| Medium (10-20 workers) | 5 | 20 |
| Heavy (50+ workers) | 10 | 50 |

## Local Token Estimation

### Usage

```python
from zcoder.agent.optimization.local_tokens import LocalTokenEstimator, estimate_tokens, estimate_tokens_detailed

estimator = LocalTokenEstimator()

# Quick estimation
tokens = estimator.estimate("Your prompt here", "claude-sonnet-5")

# Detailed estimation with breakdown
detail = estimator.estimate_detailed(
    prompt="User question",
    model="claude-sonnet-5",
    system="System prompt",
    tools=[{"name": "tool1", ...}],
    history=[{"role": "user", "content": "..."}]
)
# detail.input_tokens, detail.breakdown, etc.

# Convenience function
tokens = estimate_tokens("prompt", "claude-sonnet-5")

# Detailed convenience function
detail = estimate_tokens_detailed("prompt", "claude-sonnet-5")
```

### Performance

  - **Latency**: <0.5ms per estimation (2000+ estimates/second) — *optimized from <1ms with precompiled regex patterns*
  - **Accuracy**: ±15% for typical prompts — *improved with model-specific multipliers*
  - **No API cost**: Completely local computation
  - **Precompiled regex patterns**: Faster code detection — *new in v1.60.2*
- **Memoized multiplier cache**: Avoids redundant model lookups

### Model Multipliers

| Model | Char/Token Ratio |
|-------|------------------|
| claude-sonnet-5 | 4.0 |
| claude-opus-5 | 4.0 |
| claude-haiku-4.5 | 4.0 |
| gpt-4 | 4.0 |
| default | 3.3 |

Code prompts automatically use lower ratio (~3.0 chars/token).

## Prompt Optimization Caching

### Usage

```python
from zcoder.agent.optimization.prompt import optimize, get_optimize_cache_stats, clear_optimize_cache

# First call - cache miss
result = optimize("Write a function to sort a list", client, "claude-sonnet-5")

# Second call - cache hit (no API call)
result = optimize("Write a function to sort a list", client, "claude-sonnet-5")

# Check cache stats
stats = get_optimize_cache_stats()
# {"hits": 1, "misses": 1, "size": 1}

# Clear cache
clear_optimize_cache()
```

### Configuration

- **Cache size**: 128 entries (LRU)
- **Key**: (prompt, model, client_id)
- **Offline optimization**: Not cached (rule-based)

## Cost-Aware Model Routing

### Complexity Classification

```python
from zcoder.agent.optimization.cost import classify_complexity, select_model

complexity = classify_complexity(prompt)
# Returns: "low", "medium", or "high"

model = select_model(complexity)
# low -> claude-haiku-4-5-20251001
# medium -> claude-sonnet-5
# high -> claude-opus-5
```

### Latency-Aware Routing

```python
# Prefer faster model even for higher complexity
model = select_model("high", prefer_latency=True)
# Returns: claude-haiku-4-5-20251001 (fastest)

model = select_model("medium", prefer_latency=True)
# Returns: claude-haiku-4-5-20251001
```

### Force Model Override

```python
model = select_model("low", force="claude-opus-5")
# Returns: claude-opus-5
```

### Complexity Heuristics

| Factor | Low | Medium | High |
|--------|-----|--------|------|
| Word count | <50 | 50-500 | >500 |
| Code markers | 0 | 1-5 | >5 |
| Structural nesting | 0 | 1-3 | >3 |
| Complexity keywords | 0 | 1-2 | >2 |
| Estimated tokens | <200 | 200-1500 | >1500 |

### Prompt Optimization Integration

Before sending prompts to the model, apply token optimization heuristics to reduce token count:

```python
from zcoder.agent.optimization.tokens import optimize_prompt

optimized = optimize_prompt("Your prompt here", "claude-sonnet-5")
# Removes trailing whitespace, collapses multiple blank lines
# Can reduce token count by 10-20% for verbose prompts
```

### Optimization Savings Calculation

```python
from zcoder.agent.optimization.cost import get_optimization_savings

savings = get_optimization_savings("Your prompt here", "claude-sonnet-5")
# {"original_tokens": 150, "optimized_tokens": 120, "savings": 30, "savings_percent": 20.0}
```

## Async Concurrency Control

### WorkflowEngine

```python
from zcoder.agent.orchestration.workflow import WorkflowEngine, AsyncWorkflowStep

engine = WorkflowEngine(max_concurrent=10)

async def my_step():
    await asyncio.sleep(0.1)
    return "result"

steps = [AsyncWorkflowStep(id=f"s{i}", fn=my_step) for i in range(100)]
results = await engine.execute(steps)
```

### BatchProcessor with Backpressure

```python
from zcoder.agent.orchestration.batch import BatchProcessor, QueueFullError

processor = BatchProcessor(max_queue_size=100)

# Non-blocking enqueue
try:
    processor.enqueue("item", block=False)
except QueueFullError:
    # Handle full queue
    pass

# Blocking enqueue (async)
await processor.aenqueue("item")

# Dequeue
item = processor.dequeue()
```

### Concurrency Guidelines

| Use Case | max_concurrent | max_queue_size |
|----------|----------------|----------------|
| API calls | 10-20 | 100 |
| Local processing | 50-100 | 1000 |
| Batch jobs | 5-10 | 50 |

## Memory-Efficient Data Structures

### `__slots__` Dataclasses

```python
from zcoder.domain.models.engineering import EngineeringTask, Attempt, Checkpoint

# These classes use __slots__ - no __dict__, ~40% memory reduction
task = EngineeringTask(id="t1", task_description="test")
# task.__slots__ = ('id', 'task_description', 'status', 'created_at', 'updated_at', 'metadata')
```

### Memory-Bounded Cache

```python
from zcoder.agent.memory.cache import MemoryCache

cache = MemoryCache(max_size_mb=50)  # 50MB limit

cache.set("key", "value" * 10000)
value = cache.get("key")

print(f"Memory usage: {cache.memory_usage_mb():.1f}MB")
print(f"Items: {cache.size()}")
```

### Object Pool

```python
from zcoder.domain.models.engineering import CheckpointPool

pool = CheckpointPool(initial_size=10)

checkpoint = pool.acquire()
# Use checkpoint...
pool.release(checkpoint)  # Returns to pool, auto-reset
```

## Performance Testing

### Running Benchmarks

```bash
# Run all performance regression tests
python scripts/local_postgres.py run -- pytest tests/unit/test_performance_regression.py -v

# Run specific category
python scripts/local_postgres.py run -- pytest tests/unit/test_performance_regression.py::TestDatabasePerformance -v

# Run with local PostgreSQL
python scripts/local_postgres.py run -- pytest tests/unit/test_postgres_pool_optimization.py -v
```

### Key Performance Targets

| Metric | Target |
|--------|--------|
| Connection acquisition (avg) | <5ms |
| Connection acquisition (P99) | <20ms |
| Token estimation (10K/sec) | <0.5s |
| Token estimation latency | <1ms |
| Prompt cache speedup | Client called once |
| Job claim throughput (100) | <5s |
| Workflow 500 concurrent | <1s |
| Memory cache 10K ops | <1s |

## Monitoring

### Pool Health

```python
# Check pool status
stats = store.pool_stats()
if stats["available"] < 2:
    print("WARNING: Pool near exhaustion")

# Health check
if not store.health_check():
    print("ERROR: Database unavailable")
```

### Cache Hit Rate

```python
stats = get_optimize_cache_stats()
hit_rate = stats["hits"] / (stats["hits"] + stats["misses"])
if hit_rate < 0.5:
    print("WARNING: Low prompt cache hit rate")
```

## Recent Improvements (v1.60.2)

- **Optimized code detection**: Precompiled regex patterns for faster `_is_code()` heuristic
- **Enhanced complexity classification**: Integrated local token estimation for more accurate sizing
- **Prompt optimization heuristics**: New `optimize_prompt()` function with rule-based token reduction
- **Cost-aware model routing**: Improved token counting integration for better savings estimates
- **Memoized model multipliers**: Reduced redundant lookups in token estimation
- **Predictive model selection**: New `predict_best_model()` and `predict_best_model_for_prompt()` functions
  that analyze prompt complexity and recommend optimal models with cost savings forecasts
- **Cost-based routing**: `route_by_cost()` function routes prompts to the most cost-effective model
  based on complexity analysis and current pricing tiers
- **Spend forecasting**: `forecast_spend()` function predicts cumulative spend for batch operations
  enabling proactive cost management
- **Batch optimization**: `batch_predict_and_optimize()` processes multiple prompts with
  automated model selection and token optimization

## New Performance Targets (v1.60.2)

| Metric | Target | Notes |
|--------|--------|-------|
| Token estimation latency | <0.5ms | Per-estimation, 2000+/sec |
| Prompt cache speedup | Client called once | LRU cache hit rate >80% |
| Model routing decision | <5ms | Includes complexity analysis |
| Cost savings from optimization | 10-30% | For verbose prompts |
| Predictive model accuracy | >85% | Within one model tier of optimal |
| Spend forecast error | <15% | Compared to actual spend |

## Enhanced Model Routing

### `predict_best_model()`
Selects the optimal model based on prompt complexity and latency preferences.

```python
from zcoder.agent.optimization.cost import predict_best_model

result = predict_best_model("Write a Python function to sort a list")
# Returns: {"model": "claude-sonnet-5", "complexity": "medium", ...}
```

### `route_by_cost()`
Routes a prompt to the most cost-effective model considering both complexity and pricing.

```python
from zcoder.agent.optimization.cost import route_by_cost

result = route_by_cost("Design a microservice architecture with Kubernetes")
# Returns: {"model": "claude-sonnet-5", "complexity": "high", "in_tokens": 857, ...}
```

### `forecast_spend()`
Predicts cumulative spend for batch operations.

```python
from zcoder.agent.optimization.cost import forecast_spend

result = forecast_spend(100, {"low": 50, "medium": 30, "high": 20})
# Returns: {"total_forecasted_cost": 15.23, ...}
```

## Version History

- **v1.60.0**: Initial performance optimization suite
  - Connection pool stats, prepared statements, explain_analyze
  - Local token estimation
  - Prompt optimization LRU cache
  - Enhanced complexity classification with latency-aware routing
  - WorkflowEngine semaphore, BatchProcessor backpressure
  - `__slots__` dataclasses, MemoryCache, CheckpointPool
  - Performance regression test suite

- **v1.60.1**: Performance optimizations and enhancements
  - Optimized code detection with precompiled patterns
  - Enhanced complexity classification with token estimation
  - Prompt optimization heuristics with savings calculation
  - Cost-aware model routing improvements
  - Memoized model multipliers