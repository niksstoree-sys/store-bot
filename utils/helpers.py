"""
utils/helpers.py — Shared utility functions used across cogs.
"""

import re
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Any

import discord

from config import Config

logger = logging.getLogger("store.helpers")


# ─── Formatting Helpers ───────────────────────────────────────────────────────

def format_price(amount: float, currency: str = Config.STORE_CURRENCY) -> str:
    """Format a price value: Rp15.000"""
    if amount == int(amount):
        return f"{currency}{int(amount):,}".replace(",", ".")
    return f"{currency}{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def format_number(n: int) -> str:
    """Format large numbers with dots: 1.234.567"""
    return f"{n:,}".replace(",", ".")


def truncate(text: str, max_len: int = 100) -> str:
    """Truncate text to max_len characters."""
    return text if len(text) <= max_len else text[: max_len - 3] + "..."


def clean_input(text: str) -> str:
    """Strip and collapse whitespace."""
    return re.sub(r"\s+", " ", text.strip())


def parse_price(text: str) -> Optional[float]:
    """Parse price from string (supports '15000', '15.000', '15,000')."""
    cleaned = re.sub(r"[^\d.,]", "", text).replace(".", "").replace(",", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def timestamp_str() -> str:
    return utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")


# ─── Permission Helpers ───────────────────────────────────────────────────────

def is_admin(member: discord.Member) -> bool:
    """Check if member has ADMIN_ROLE_ID or OWNER_ROLE_ID."""
    admin_ids = {Config.ADMIN_ROLE_ID, Config.OWNER_ROLE_ID}
    return (
        any(role.id in admin_ids for role in member.roles)
        or member.guild_permissions.administrator
    )


def is_owner(member: discord.Member) -> bool:
    return (
        any(role.id == Config.OWNER_ROLE_ID for role in member.roles)
        or member.guild_permissions.administrator
    )


# ─── Discord Helpers ──────────────────────────────────────────────────────────

async def safe_send_dm(user: discord.User | discord.Member, **kwargs: Any) -> bool:
    """
    Attempt to send a DM. Returns True on success, False if DMs are closed.
    """
    try:
        await user.send(**kwargs)
        return True
    except (discord.Forbidden, discord.HTTPException):
        return False


async def send_log(
    bot: discord.Client,
    embed: discord.Embed,
    webhook_url: Optional[str] = None,
) -> None:
    """
    Send a log embed to the log channel (and optionally a webhook).
    """
    try:
        if Config.LOG_CHANNEL_ID:
            channel = bot.get_channel(Config.LOG_CHANNEL_ID)
            if channel and isinstance(channel, discord.TextChannel):
                await channel.send(embed=embed)
    except Exception as exc:
        logger.warning(f"Failed to send log to channel: {exc}")

    if webhook_url:
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                webhook = discord.Webhook.from_url(webhook_url, session=session)
                await webhook.send(embed=embed)
        except Exception as exc:
            logger.warning(f"Failed to send webhook log: {exc}")


def make_invoice_number(user_id: int) -> str:
    now = datetime.now()
    return f"INV-{now.strftime('%Y%m%d%H%M%S')}-{user_id % 10000:04d}"


def chunk_list(lst: list[Any], size: int) -> list[list[Any]]:
    """Split list into chunks of `size`."""
    return [lst[i : i + size] for i in range(0, len(lst), size)]


async def confirm_action(
    interaction: discord.Interaction,
    message: str,
    timeout: float = 30.0,
) -> bool:
    """
    Send a confirmation prompt with Yes/No buttons.
    Returns True if user confirms, False if cancelled or timed out.
    """
    from utils.views import ConfirmView

    view = ConfirmView(interaction.user.id, timeout=timeout)
    await interaction.response.send_message(message, view=view, ephemeral=True)
    await view.wait()
    return view.confirmed


def generate_transcript_html(
    channel_name: str,
    messages: list[dict[str, Any]],
    ticket_info: dict[str, Any],
) -> str:
    """Generate an HTML transcript from a list of message dicts."""
    rows = ""
    for msg in messages:
        avatar = msg.get("avatar", "")
        author = msg.get("author", "Unknown")
        timestamp = msg.get("timestamp", "")
        content = msg.get("content", "").replace("<", "&lt;").replace(">", "&gt;")
        avatar_html = f'<img src="{avatar}" class="avatar">' if avatar else '<div class="avatar-placeholder"></div>'
        rows += f"""
        <div class="message">
            <div class="author-section">
                {avatar_html}
                <span class="author">{author}</span>
                <span class="timestamp">{timestamp}</span>
            </div>
            <div class="content">{content}</div>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Transcript — {channel_name}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: #313338; color: #dbdee1; font-family: 'gg sans', 'Noto Sans', Arial, sans-serif; padding: 20px; }}
  h1 {{ color: #ffffff; font-size: 1.4rem; margin-bottom: 4px; }}
  .meta {{ color: #949ba4; font-size: 0.85rem; margin-bottom: 20px; }}
  .message {{ background: #383a40; border-radius: 8px; padding: 12px 16px; margin-bottom: 8px; }}
  .author-section {{ display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }}
  .avatar {{ width: 32px; height: 32px; border-radius: 50%; }}
  .avatar-placeholder {{ width: 32px; height: 32px; border-radius: 50%; background: #5865f2; }}
  .author {{ color: #ffffff; font-weight: 600; font-size: 0.9rem; }}
  .timestamp {{ color: #949ba4; font-size: 0.75rem; }}
  .content {{ color: #dbdee1; font-size: 0.9rem; line-height: 1.5; white-space: pre-wrap; word-break: break-word; }}
  .header {{ background: #2b2d31; border-radius: 8px; padding: 16px; margin-bottom: 20px; border-left: 4px solid #5865f2; }}
</style>
</head>
<body>
<div class="header">
  <h1>📋 Transcript — #{channel_name}</h1>
  <div class="meta">
    Ticket oleh: <strong>{ticket_info.get('username', 'Unknown')}</strong> |
    Status: <strong>{ticket_info.get('status', 'closed').upper()}</strong> |
    Dibuat: {ticket_info.get('created_at', '')} |
    Ditutup: {ticket_info.get('closed_at', '')}
  </div>
</div>
{rows}
<p style="color:#949ba4;font-size:0.75rem;margin-top:20px;text-align:center;">
  Generated by Discord Store Bot • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
</p>
</body>
</html>"""
