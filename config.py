"""
config.py — Central configuration management for Discord Store Bot.
Loads and validates all environment variables.
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Central configuration class. All settings loaded from .env"""

    # ─── Discord ──────────────────────────────────────────────────────────────
    TOKEN: str = os.getenv("TOKEN", "")
    GUILD_ID: int = int(os.getenv("GUILD_ID", "0"))
    ADMIN_ROLE_ID: int = int(os.getenv("ADMIN_ROLE_ID", "0"))
    OWNER_ROLE_ID: int = int(os.getenv("OWNER_ROLE_ID", "0"))
    TICKET_CATEGORY_ID: int = int(os.getenv("TICKET_CATEGORY_ID", "0"))
    LOG_CHANNEL_ID: int = int(os.getenv("LOG_CHANNEL_ID", "0"))
    STORE_CHANNEL_ID: int = int(os.getenv("STORE_CHANNEL_ID", "0"))

    # ─── Database ─────────────────────────────────────────────────────────────
    DATABASE_PATH: str = os.getenv("DATABASE_PATH", "database/store.db")

    # ─── Bot Settings ─────────────────────────────────────────────────────────
    BOT_PREFIX: str = os.getenv("BOT_PREFIX", "!")
    BOT_STATUS: str = os.getenv("BOT_STATUS", "Melayani Pembelian")
    BOT_ACTIVITY: str = os.getenv("BOT_ACTIVITY", "watching")

    # ─── Store Settings ───────────────────────────────────────────────────────
    STORE_NAME: str = os.getenv("STORE_NAME", "Premium Store")
    STORE_DESCRIPTION: str = os.getenv(
        "STORE_DESCRIPTION",
        "Temukan produk digital berkualitas dengan harga terjangkau!"
    )
    STORE_COLOR: int = int(os.getenv("STORE_COLOR", "0x5865F2"), 16)
    STORE_CURRENCY: str = os.getenv("STORE_CURRENCY", "Rp")

    # ─── Webhook Logging ──────────────────────────────────────────────────────
    LOG_WEBHOOK_URL: str = os.getenv("LOG_WEBHOOK_URL", "")

    # ─── Backup Settings ──────────────────────────────────────────────────────
    BACKUP_INTERVAL_HOURS: int = int(os.getenv("BACKUP_INTERVAL_HOURS", "24"))
    BACKUP_MAX_FILES: int = int(os.getenv("BACKUP_MAX_FILES", "7"))

    # ─── Notification Thresholds ──────────────────────────────────────────────
    LOW_STOCK_THRESHOLD: int = int(os.getenv("LOW_STOCK_THRESHOLD", "5"))

    # ─── Pagination ───────────────────────────────────────────────────────────
    ITEMS_PER_PAGE: int = int(os.getenv("ITEMS_PER_PAGE", "10"))

    # ─── Embed Colors ─────────────────────────────────────────────────────────
    COLOR_PRIMARY: int = 0x5865F2    # Blurple
    COLOR_SUCCESS: int = 0x57F287    # Green
    COLOR_WARNING: int = 0xFEE75C    # Yellow
    COLOR_ERROR: int = 0xED4245      # Red
    COLOR_INFO: int = 0x5865F2       # Blue
    COLOR_GOLD: int = 0xFFD700       # Gold (for premium)
    COLOR_DARK: int = 0x2F3136       # Dark

    # ─── Ticket Settings ──────────────────────────────────────────────────────
    TICKET_AUTO_CLOSE_HOURS: int = 24  # Auto-close ticket after 24h of inactivity

    @classmethod
    def validate(cls) -> None:
        """Validate required configuration values on startup."""
        errors: list[str] = []

        if not cls.TOKEN:
            errors.append("TOKEN is required")
        if cls.GUILD_ID == 0:
            errors.append("GUILD_ID is required")
        if cls.ADMIN_ROLE_ID == 0:
            errors.append("ADMIN_ROLE_ID is required")
        if cls.LOG_CHANNEL_ID == 0:
            errors.append("LOG_CHANNEL_ID is required")

        if errors:
            raise EnvironmentError(
                f"Missing required configuration:\n" + "\n".join(f"  - {e}" for e in errors)
            )
