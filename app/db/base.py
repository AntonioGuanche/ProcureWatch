"""Backward-compat shim. Real Base is in app.models.base."""
from app.models.base import Base  # noqa: F401

__all__ = ["Base"]
