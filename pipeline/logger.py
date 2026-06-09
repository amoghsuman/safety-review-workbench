"""Structured per-session and summary logging"""

import logging
import logging.handlers
import os
from pathlib import Path

LOG_LEVEL     = os.getenv("LOG_LEVEL", "INFO")
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_LOG_DIR      = _PROJECT_ROOT / "logs"
_LOG_FILE     = _LOG_DIR / "pipeline.log"

_FMT = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

_configured: set[str] = set()


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if name in _configured:
        return logger

    level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)
    logger.setLevel(level)
    logger.propagate = False

    _LOG_DIR.mkdir(parents=True, exist_ok=True)

    fh = logging.handlers.RotatingFileHandler(
        _LOG_FILE,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(_FMT)

    ch = logging.StreamHandler()
    ch.setLevel(level)
    ch.setFormatter(_FMT)

    logger.addHandler(fh)
    logger.addHandler(ch)
    _configured.add(name)
    return logger


def log_session_result(
    logger: logging.Logger,
    session_id: str,
    verdict: str,
    flag_count: int,
    duration_seconds: float,
) -> None:
    logger.info(
        "SESSION | %s | verdict=%s | flags=%d | time=%.2fs",
        session_id, verdict, flag_count, duration_seconds,
    )


def log_batch_summary(
    logger: logging.Logger,
    total: int,
    clean: int,
    flagged: int,
    severe: int,
    errors: int,
    elapsed_minutes: float,
) -> None:
    sep = "=" * 60
    logger.info(sep)
    logger.info("BATCH RUN COMPLETE")
    logger.info(sep)
    logger.info("  Total processed  : %d", total)
    logger.info("  CLEAN            : %d", clean)
    logger.info("  FLAGGED          : %d", flagged)
    logger.info("  SEVERE           : %d", severe)
    logger.info("  Errors / skipped : %d", errors)
    logger.info("  Elapsed          : %.1f min", elapsed_minutes)
    logger.info(sep)


def log_error(logger: logging.Logger, session_id: str, error: Exception) -> None:
    logger.error(
        "ERROR | %s | %s: %s",
        session_id, type(error).__name__, str(error),
    )
    logger.debug("Traceback for session %s:", session_id, exc_info=error)
