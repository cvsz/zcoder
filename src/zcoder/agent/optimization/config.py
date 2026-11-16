"""Shared configuration and constants for optimization modules.

This module holds constants that are shared across the optimization
sub-modules without creating circular import dependencies.
"""

# Model-specific character-to-token multipliers
# Based on typical tokenizer behavior for each model family
TIER_MODELS = ["claude-haiku-4-5-20251001", "claude-sonnet-5", "claude-opus-5"]
