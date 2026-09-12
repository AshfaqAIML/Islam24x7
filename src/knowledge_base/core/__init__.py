"""Shared low-level primitives used across the knowledge base.

Kept dependency-free and framework-agnostic so any pipeline stage can
import them without pulling in the rest of the system.
"""

from knowledge_base.core import hashing

__all__ = ["hashing"]
