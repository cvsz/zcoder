"""Connection pooling for model API requests for Phase 15/16.

Provides connection pooling and reuse for model API requests to reduce
latency and improve throughput for multiple concurrent requests.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum


class PoolStatus(Enum):
    """Status of the connection pool."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    EXHAUSTED = "exhausted"
    ERROR = "error"


@dataclass
class PoolMetrics:
    """Metrics for a connection pool."""

    total_connections: int = 0
    active_connections: int = 0
    idle_connections: int = 0
    peak_connections: int = 0
    total_requests: int = 0
    total_wait_time: float = 0.0
    cache_hits: int = 0
    cache_misses: int = 0


@dataclass
class PooledConnection:
    """A pooled connection to a model API."""

    model_id: str
    provider: str
    connection_string: str
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    usage_count: int = 0
    ttl_seconds: int | None = None  # Time-to-live for the connection
    error_count: int = 0
    last_error: str | None = None

    def is_active(self) -> bool:
        """Check if the connection is currently active."""
        return True  # Connection is always "active" in pooled model

    def mark_used(self) -> None:
        """Mark the connection as used."""
        self.last_used = time.time()
        self.usage_count += 1

    def is_stale(self) -> bool:
        """Check if the connection should be retired based on TTL."""
        if self.ttl_seconds is None:
            return False
        return time.time() - self.created_at > self.ttl_seconds

    def record_error(self, error: str) -> None:
        """Record an error from using this connection."""
        self.error_count += 1
        self.last_error = error

    def get_metrics(self) -> PoolMetrics:
        """Get metrics for this connection."""
        return PoolMetrics(
            total_connections=1,
            active_connections=1,
            idle_connections=0,
            peak_connections=1 if self.usage_count == 0 else 0,
            total_requests=self.usage_count,
        )


class ConnectionPool:
    """Manages a pool of connections to model APIs."""

    def __init__(
        self,
        max_size: int = 10,
        ttl_seconds: int | None = None,
        max_usage_per_connection: int | None = None,
        geo_constraint: str | None = None,
    ) -> None:
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self.max_usage_per_connection = max_usage_per_connection
        self.geo_constraint = geo_constraint

        # Pool of connections organized by (provider, model_id)
        self._pools: dict[tuple[str, str], OrderedDict[PooledConnection, PooledConnection]] = {}
        self._metrics = PoolMetrics()

    def _get_pool_key(self, provider: str, model_id: str) -> tuple[str, str]:
        """Get the pool key for a provider/model combination."""
        return (provider, model_id)

    def _create_connection(
        self, provider: str, model_id: str, connection_string: str | None = None
    ) -> PooledConnection:
        """Create a new connection to add to the pool."""
        key = self._get_pool_key(provider, model_id)

        if key not in self._pools:
            self._pools[key] = OrderedDict()

        conn = PooledConnection(
            model_id=model_id,
            provider=provider,
            connection_string=connection_string or "",
            ttl_seconds=self.ttl_seconds,
        )

        # Add to pool, evicting oldest if at max size
        pool = self._pools[key]
        if len(pool) >= self.max_size:
            # Remove oldest connection
            oldest_key = next(iter(pool))
            pool.pop(oldest_key)

        pool[conn] = conn  # Will be re-ordered on access
        # Move to end (most recently used)
        pool.move_to_end(conn)

        self._metrics.total_connections += 1
        if len(pool) > self._metrics.peak_connections:
            self._metrics.peak_connections = len(pool)

        return conn

    def get_connection(
        self, provider: str, model_id: str, force_new: bool = False
    ) -> PooledConnection | None:
        """Get a connection from the pool."""
        key = self._get_pool_key(provider, model_id)

        if not force_new:
            pool = self._pools.get(key, OrderedDict())
            if pool:
                # Get most recently used connection that's not stale
                for conn in reversed(list(pool.values())):
                    if not conn.is_stale() and conn.usage_count < (
                        self.max_usage_per_connection or float("inf")
                    ):
                        conn.mark_used()
                        self._metrics.cache_hits += 1
                        return conn

                # All connections are stale or at max usage; create fresh one
                self._metrics.cache_misses += 1
                return self._create_connection(provider, model_id)

        # Force new connection
        self._metrics.cache_misses += 1
        return self._create_connection(provider, model_id)

    def release_connection(self, conn: PooledConnection) -> None:
        """Release a connection back to the pool (no-op for pooled connections)."""
        # Connections are automatically managed; just mark as available
        pass

    def return_connection(self, conn: PooledConnection) -> None:
        """Return a connection to the pool, potentially evicting if needed."""
        key = self._get_pool_key(conn.provider, conn.model_id)
        pool = self._pools.get(key)

        if pool and conn in pool:
            # Move to end (most recently used)
            pool.move_to_end(conn)

    def cleanup(self) -> None:
        """Clean up stale and expired connections."""
        for _key, pool in self._pools.items():
            # Remove stale connections
            keys_to_remove = []
            for conn in pool.keys():
                if conn.is_stale():
                    keys_to_remove.append(conn)

            for key_to_remove in keys_to_remove:
                pool.pop(key_to_remove, None)
                self._metrics.total_connections -= 1

            # Trim to max size
            while len(pool) > self.max_size:
                oldest = next(iter(pool))
                pool.pop(oldest)
                self._metrics.total_connections -= 1

    def get_metrics(self) -> PoolMetrics:
        """Get overall pool metrics."""
        # Update idle count
        for pool in self._pools.values():
            for conn in pool.values():
                if conn.usage_count == 0:
                    self._metrics.idle_connections += 1

        return self._metrics


# Global pool instance
_connection_pool: ConnectionPool | None = None


def get_connection_pool(
    max_size: int = 10,
    ttl_seconds: int | None = None,
    max_usage_per_connection: int | None = None,
    geo_constraint: str | None = None,
) -> ConnectionPool:
    """Get the global connection pool instance."""
    global _connection_pool
    if _connection_pool is None:
        _connection_pool = ConnectionPool(
            max_size=max_size,
            ttl_seconds=ttl_seconds,
            max_usage_per_connection=max_usage_per_connection,
            geo_constraint=geo_constraint,
        )
    return _connection_pool


def get_connection(
    provider: str,
    model_id: str,
    force_new: bool = False,
) -> PooledConnection | None:
    """Get a connection from the global pool."""
    pool = get_connection_pool(
        max_size=10,
        ttl_seconds=None,
        max_usage_per_connection=100,
        geo_constraint=None,
    )
    return pool.get_connection(provider, model_id, force_new=force_new)


def return_connection(conn: PooledConnection) -> None:
    """Return a connection to the global pool."""
    pool = get_connection_pool()
    pool.return_connection(conn)


def cleanup_pool() -> None:
    """Clean up the global connection pool."""
    global _connection_pool
    if _connection_pool:
        _connection_pool.cleanup()
