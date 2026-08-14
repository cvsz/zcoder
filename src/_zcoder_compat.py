"""Temporary aliases for the pre-src-layout import surface.

Internal code is being normalized to ``zcoder.*`` imports incrementally. These
aliases preserve existing imports and third-party integrations during that
transition without duplicating implementation code.
"""
import sys
from importlib import import_module


def alias_module(legacy_name, target_name, namespace):
    """Bind a legacy module name to the canonical package module."""
    module = import_module(target_name)
    namespace.update(module.__dict__)
    sys.modules[legacy_name] = module
