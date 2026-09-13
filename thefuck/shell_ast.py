"""Structural analysis of shell commands, backed by bashlex.

Personal fork only: bashlex is GPL-3+ licensed while thefuck is MIT,
so this combination must not be distributed.
"""
import six

try:
    import bashlex
except ImportError:
    bashlex = None


AST_AVAILABLE = bashlex is not None and six.PY3
