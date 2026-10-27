"""Optional observability bridge for provider-neutral model calls."""

from contextlib import nullcontext
from importlib import import_module


def trace_model_call(*, provider: str, model: str, operation: str = "inference"):
    """Return an observability context without a static adapter dependency."""
    try:
        adapter = import_module(".".join(("zcoder", "infrastructure", "observability", "otel")))
        return adapter.trace_model_call(provider=provider, model=model, operation=operation)
    except ImportError:
        return nullcontext()
