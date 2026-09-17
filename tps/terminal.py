"""Backward-compatible import for the provider-neutral Architect handler."""

from tps.architect.service import architect_handler

terminal_handler = architect_handler

__all__ = ["architect_handler", "terminal_handler"]
