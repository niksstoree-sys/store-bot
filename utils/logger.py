"""
utils/logger.py — Centralized logging configuration.
Outputs to both console and rotating file in logs/ directory.
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from datetime import datetime


def setup_logging(log_level: str = "INFO") -> None:
    """Configure root logger with console + file handlers."""
    os.makedirs("logs", exist_ok=True)

    log_format = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # ─── Console Handler ──────────────────────────────────────────────────────
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_format)
    console_handler.setLevel(logging.INFO)
    root_logger.addHandler(console_handler)

    # ─── File Handler (rotating, max 5MB × 5 files) ───────────────────────────
    today = datetime.now().strftime("%Y-%m-%d")
    file_handler = RotatingFileHandler(
        filename=f"logs/store-bot-{today}.log",
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(log_format)
    file_handler.setLevel(logging.DEBUG)
    root_logger.addHandler(file_handler)

    # Silence noisy discord.py internals
    logging.getLogger("discord").setLevel(logging.WARNING)
    logging.getLogger("discord.http").setLevel(logging.WARNING)
    logging.getLogger("discord.gateway").setLevel(logging.WARNING)

    logging.getLogger("store").info("Logging initialized.")
