"""String-backed Enum compatibility primitives."""

import enum


# שומרรูปแบบ str(member) เดิมไว้ พร้อมคงการ serialize เป็น string
class StringEnum(str, enum.Enum):  # noqa: UP042
    """A string enum that preserves the standard Enum string representation."""
