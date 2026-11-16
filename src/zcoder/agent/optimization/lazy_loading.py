"""Lazy model loading with prewarm for Phase 15/16.

Provides lazy loading of model implementations with prewarm capability
to reduce initial latency and connection pooling for model API requests.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from zcoder.agent.models.registry import (
    MODEL_CATALOG,
)


class LoadStatus(Enum):
    """Status of model loading."""

    NOT_LOADED = "not_loaded"
    LOADING = "loading"
    LOADED = "loaded"
    FAILED = "failed"
    UNLOADED = "unloaded"


@dataclass
class ModelLoadInfo:
    """Information about a loaded model."""

    model_id: str
    status: LoadStatus = LoadStatus.NOT_LOADED
    loaded_at: float = 0.0
    ttr: float = 0.0  # time to ready
    error: str | None = None
    provider: str | None = None
    context_window: int = 1_000_000
    price_in: float = 0.0
    price_out: float = 0.0


@dataclass
class LazyModel:
    """Lazy-loaded model wrapper."""

    model_id: str
    on_load: Callable | None = None
    on_unload: Callable | None = None
    auto_unload: bool = False
    ttl_seconds: int | None = None  # Time-to-live for cached model
    _load_time: float = 0.0
    _last_access: float = 0.0
    _instance: Any = None  # Actual model instance
    _load_status: LoadStatus = LoadStatus.NOT_LOADED
    _provider: str | None = None

    def is_loaded(self) -> bool:
        """Check if the model is currently loaded."""
        return self._load_status == LoadStatus.LOADED

    def is_stale(self) -> bool:
        """Check if the model should be considered stale (TTL expired)."""
        if self.ttl_seconds is None:
            return False
        return time.time() - self._last_access > self.ttl_seconds

    def mark_accessed(self) -> None:
        """Mark the model as recently accessed."""
        self._last_access = time.time()

    def get_provider(self) -> str | None:
        """Get the provider for this model."""
        return self._provider

    def set_provider(self, provider: str | None) -> None:
        """Set the provider for this model."""
        self._provider = provider

    def get_load_status(self) -> LoadStatus:
        """Get the current load status."""
        return self._load_status

    def set_load_status(self, status: LoadStatus) -> None:
        """Set the load status."""
        self._load_status = status

    def load(self) -> Any:
        """Load the model instance. To be implemented by subclass or caller."""
        if self.is_loaded() and not self.is_stale():
            return self._instance

        self._load_status = LoadStatus.LOADING
        start_time = time.time()

        # Model catalog lookups
        catalog_info = MODEL_CATALOG.get(self.model_id, {})
        self._provider = catalog_info.get("tier", "unknown")
        self.context_window = catalog_info.get("context_window", 1_000_000)
        self.price_in = catalog_info.get("price_in", 0.0)
        self.price_out = catalog_info.get("price_out", 0.0)

        # Call on_load callback if provided
        if self.on_load:
            try:
                self._instance = self.on_load()
            except Exception as e:
                self._load_status = LoadStatus.FAILED
                self.error = str(e)
                raise

        self._load_time = time.time() - start_time
        self._load_status = LoadStatus.LOADED
        self.mark_accessed()
        return self._instance

    def unload(self) -> None:
        """Unload the model instance."""
        if self.on_unload:
            try:
                self.on_unload()
            except Exception:  # nosec
                pass
        self._instance = None
        self._load_status = LoadStatus.UNLOADED


class ModelLoader:
    """Manages lazy model loading with connection pooling and prewarm."""

    def __init__(self) -> None:
        self._models: dict[str, LazyModel] = {}
        self._load_order: list[str] = []
        self._pool: dict[str, Any] = {}  # Pool of loaded model instances
        self._prewarm_models: list[str] = []

    def register(
        self,
        model_id: str,
        on_load: Callable | None = None,
        on_unload: Callable | None = None,
        auto_unload: bool = False,
        ttl_seconds: int | None = None,
    ) -> LazyModel:
        """Register a model for lazy loading."""
        if model_id in self._models:
            raise ValueError(f"Model {model_id} is already registered")

        lazy_model = LazyModel(
            model_id=model_id,
            on_load=on_load,
            on_unload=on_unload,
            auto_unload=auto_unload,
            ttl_seconds=ttl_seconds,
        )
        self._models[model_id] = lazy_model
        self._load_order.append(model_id)
        return lazy_model

    def get(self, model_id: str) -> LazyModel | None:
        """Get a registered model by ID."""
        return self._models.get(model_id)

    def load_model(self, model_id: str) -> Any:
        """Load a model instance, using cache if available."""
        lazy_model = self._models.get(model_id)
        if not lazy_model:
            raise ValueError(f"Model {model_id} is not registered")

        # Check if already loaded and not stale
        if lazy_model.is_loaded() and not lazy_model.is_stale():
            lazy_model.mark_accessed()
            return lazy_model._instance

        # Unload any previously loaded model to free resources
        if lazy_model._load_status == LoadStatus.LOADED and not lazy_model.is_stale():
            # Check if it's the same model we want
            pass

        # Load the model
        instance = lazy_model.load()
        self._pool[model_id] = instance
        return instance

    def unload_model(self, model_id: str) -> None:
        """Unload a model instance."""
        lazy_model = self._models.get(model_id)
        if not lazy_model:
            return

        lazy_model.unload()
        self._pool.pop(model_id, None)

    def prewarm(self, model_ids: list[str]) -> None:
        """Prewarm specified models so they're ready for immediate use."""
        self._prewarm_models = model_ids
        for model_id in model_ids:
            lazy_model = self._models.get(model_id)
            if not lazy_model:
                continue
            if lazy_model.is_loaded():
                continue
            try:
                lazy_model.load()
            except Exception:  # nosec
                # Prewarm failure is non-fatal; model will load on demand
                pass

    def cleanup_stale(self) -> None:
        """Clean up stale models that have exceeded their TTL."""
        _ = time.time()
        for _model_id, lazy_model in self._models.items():
            if lazy_model.is_loaded() and lazy_model.is_stale():
                lazy_model.unload()


# Global model loader instance
_model_loader: ModelLoader | None = None


def get_model_loader() -> ModelLoader:
    """Get the global model loader instance."""
    global _model_loader
    if _model_loader is None:
        _model_loader = ModelLoader()
    return _model_loader


def lazy_model(
    model_id: str,
    on_load: Callable | None = None,
    on_unload: Callable | None = None,
    auto_unload: bool = False,
    ttl_seconds: int | None = None,
) -> LazyModel:
    """Convenience function to register and get a lazy model."""
    loader = get_model_loader()
    return loader.register(
        model_id=model_id,
        on_load=on_load,
        on_unload=on_unload,
        auto_unload=auto_unload,
        ttl_seconds=ttl_seconds,
    )
