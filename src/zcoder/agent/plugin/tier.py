"""Plugin tier system for zcoder.

Defines the four plugin tiers with precedence ordering:
- PREPEND (0): Organization prepend tier (outermost)
- USER (1): User-installed plugins
- APPEND (2): Organization append tier
- BUILTIN (3): Built-in plugins (innermost)

Lower numeric value = higher precedence (runs first, can override).
"""

from enum import IntEnum


class PluginTier(IntEnum):
    """Plugin execution tier with precedence ordering."""

    PREPEND = 0  # Organization prepend (outermost, highest precedence)
    USER = 1  # User-installed plugins
    APPEND = 2  # Organization append
    BUILTIN = 3  # Built-in plugins (innermost, lowest precedence)

    @classmethod
    def from_string(cls, s: str) -> "PluginTier":
        """Parse tier from string."""
        mapping = {
            "prepend": cls.PREPEND,
            "user": cls.USER,
            "append": cls.APPEND,
            "builtin": cls.BUILTIN,
        }
        if s not in mapping:
            raise ValueError(f"Unknown tier: {s}. Valid tiers: {list(mapping.keys())}")
        return mapping[s]

    @classmethod
    def all_tiers(cls) -> list["PluginTier"]:
        """Return all tiers in precedence order."""
        return [cls.PREPEND, cls.USER, cls.APPEND, cls.BUILTIN]

    @property
    def can_override_user(self) -> bool:
        """Whether this tier can override user-tier decisions."""
        return self <= self.USER

    @property
    def is_org_tier(self) -> bool:
        """Whether this is an organization-controlled tier."""
        return self in (self.PREPEND, self.APPEND)

    @property
    def is_builtin_or_org(self) -> bool:
        """Whether this is builtin or org tier (for telemetry gate)."""
        return self in (self.PREPEND, self.APPEND, self.BUILTIN)

    def __str__(self) -> str:
        return self.name.lower()
