"""Lazy structlog logger.

Importing structlog is expensive: it pulls in asyncio, the stdlib logging
module, and most of rich. Commands that only render help never log anything,
so ``slackx`` hands out a proxy instead of a bound logger and imports
structlog on the first log call.

Usage is the same as ``structlog.get_logger(__name__)``::

    from slackx._log import get_logger

    log = get_logger(__name__)
"""

from __future__ import annotations

from typing import Any


class _LazyLogger:
    """Stand-in for a structlog logger that resolves on first attribute use."""

    def __init__(self, name: str) -> None:
        self._name = name
        self._logger: Any = None

    def __getattr__(self, name: str) -> Any:
        logger = self.__dict__.get("_logger")
        if logger is None:
            import structlog

            logger = structlog.get_logger(self._name)
            self.__dict__["_logger"] = logger
        return getattr(logger, name)


def get_logger(name: str) -> Any:
    """Return a logger that imports structlog only when it is first used."""
    return _LazyLogger(name)
