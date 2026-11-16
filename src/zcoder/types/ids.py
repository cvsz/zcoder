"""
zcoder.types.ids — Branded opaque ID types.

Branded strings make structurally identical values non-interchangeable at the
type level: a ModelId cannot be passed where a RequestId is expected. This is
the Python equivalent of deepseek-harness's @zharness/dsh-brand package.

brandX() changes only the static type; performs no runtime validation.
Once branded, the id compares, logs, serializes to JSON, and crosses the
wire as an ordinary string.
"""

from __future__ import annotations

from typing import Annotated, TypeVar, cast

T = TypeVar("T")

BRAND: str = "__brand__"


def brandString(value: str) -> str:
    """Brand a raw string as a nominal type.

    Changes only the static type; performs no runtime validation. Validate
    domain grammar before calling when the owning type has one. Once branded,
    the id compares, logs, serializes to JSON, and crosses the wire as an
    ordinary string.
    """
    return value


def brandNumber(value: float) -> float:
    """Brand a raw number as a nominal type.

    Returns the original number and performs no validation.
    """
    return value


# ── Model ID brand ──────────────────────────────────────────────────────────

ModelId = Annotated[str, "ModelId"]


def brandModelId(value: str) -> ModelId:
    return cast(ModelId, brandString(value))


# ── Request ID brand ────────────────────────────────────────────────────────

RequestId = Annotated[str, "RequestId"]


def brandRequestId(value: str) -> RequestId:
    return cast(RequestId, brandString(value))


# ── ToolCall ID brand ───────────────────────────────────────────────────────

ToolCallId = Annotated[str, "ToolCallId"]


def brandToolCallId(value: str) -> ToolCallId:
    return cast(ToolCallId, brandString(value))
