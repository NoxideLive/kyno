"""Progress logging for self-improve runner (stderr, line-unbuffered)."""

from __future__ import annotations

import logging
import sys
from typing import Any


class _FlushStreamHandler(logging.StreamHandler):
    def emit(self, record: logging.LogRecord) -> None:
        super().emit(record)
        self.flush()


_logger: logging.Logger | None = None


def configure_logging(*, verbose: bool = False) -> logging.Logger:
    global _logger
    handler = _FlushStreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    root = logging.getLogger("self_improve")
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    root.propagate = False
    _logger = root
    return root


def get_logger() -> logging.Logger:
    if _logger is None:
        return configure_logging()
    return _logger


def info(msg: str, *args: Any) -> None:
    get_logger().info(msg, *args)


def debug(msg: str, *args: Any) -> None:
    get_logger().debug(msg, *args)


def warn(msg: str, *args: Any) -> None:
    get_logger().warning(msg, *args)
